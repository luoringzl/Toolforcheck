from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .config import QualityConfig


def _gray_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32)


def blur_score(image: Image.Image) -> float:
    a = _gray_array(image)
    if min(a.shape) < 3:
        return 0.0
    lap = -4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
    return float(np.var(lap))


def glare_metrics(image: Image.Image) -> tuple[float, float]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    bright = (rgb.min(axis=2) >= 245)
    ratio = float(bright.mean())
    # Largest bright run is a conservative proxy for a contiguous glare patch.
    largest = 0
    for row in bright[::max(1, bright.shape[0] // 250)]:
        padded = np.r_[False, row, False]
        changes = np.flatnonzero(padded[1:] != padded[:-1])
        if len(changes) >= 2:
            largest = max(largest, int(np.max(changes[1::2] - changes[::2])))
    return ratio, largest / max(1, bright.shape[1])


def detect_rotation(image: Image.Image) -> float | None:
    """使用OpenCV直线角度估计轻微倾斜，不依赖Tesseract方向模型。"""
    try:
        import cv2

        gray = np.asarray(image.convert("L"), dtype=np.uint8)
        edges = cv2.Canny(gray, 60, 180)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=max(60, gray.shape[1] // 8),
            minLineLength=max(80, gray.shape[1] // 5), maxLineGap=20,
        )
        if lines is None:
            return None
        angles = []
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            while angle > 45:
                angle -= 90
            while angle < -45:
                angle += 90
            angles.append(angle)
        return abs(float(np.median(angles))) if angles else None
    except Exception:
        return None


def assess_id_image(image: Image.Image, cfg: QualityConfig) -> list[str]:
    reasons: list[str] = []
    w, h = image.size
    if max(w, h) < cfg.min_width or min(w, h) < cfg.min_height:
        reasons.append(f"图片分辨率不足（{w}×{h}）")
    b = blur_score(image)
    if b < cfg.blur_variance_min:
        reasons.append(f"图片模糊（清晰度评分 {b:.1f}）")
    glare, region = glare_metrics(image)
    if glare > cfg.glare_ratio_max or region > cfg.glare_largest_region_ratio_max:
        reasons.append("图片存在严重反光")
    # 横向、竖向均允许；90°方向不作为退回原因。真正的轻度严重歪斜仍由
    # 直线角度检测处理，OCR会自动尝试四个正交方向。
    rotation = detect_rotation(image)
    if rotation is not None and rotation > cfg.severe_rotation_degrees:
        reasons.append(f"图片严重倾斜或旋转（约 {rotation:.0f}°）")
    return reasons


def red_stamp_ratio(image: Image.Image) -> float:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    red = (rgb[:, :, 0] > 120) & (rgb[:, :, 0] > rgb[:, :, 1] * 1.30) & (rgb[:, :, 0] > rgb[:, :, 2] * 1.30)
    return float(red.mean())


def has_red_stamp(image: Image.Image) -> bool:
    # 工作证明中公章通常占页面面积的0.1%以上；阈值保守，结果只表示检测到红章区域。
    return red_stamp_ratio(image) >= 0.001


def assess_id_photo(image: Image.Image) -> list[str]:
    """检查证件照是否为近似二寸、竖版、彩色半身照；不做文字识别。"""
    reasons: list[str] = []
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    h, w = rgb.shape[:2]
    ratio = w / max(1, h)
    if h <= w or not 0.62 <= ratio <= 0.82:
        reasons.append(f"证件照应为二寸竖版比例（当前宽高比 {ratio:.2f}）")
    # 彩色照片三个通道必须存在可感知差异；灰度或黑白扫描件会接近0。
    channel_spread = np.mean(np.max(rgb, axis=2).astype(np.float32) - np.min(rgb, axis=2))
    if channel_spread < 4.0:
        reasons.append("证件照应为半身彩色照片，当前图片接近黑白或灰度")

    # 用OpenCV随包自带的人脸分类器确认画面中有正面人物，且人脸占比符合半身照。
    try:
        import cv2

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4,
            minSize=(max(24, w // 10), max(24, h // 10)),
        )
        if len(faces) == 0:
            reasons.append("未检测到符合证件照要求的正面人像，请确认是半身正面照片")
        else:
            _, y, fw, fh = max(faces, key=lambda item: item[2] * item[3])
            face_ratio = (fw * fh) / max(1, w * h)
            if not 0.025 <= face_ratio <= 0.38 or y > h * 0.48:
                reasons.append("人像构图不符合二寸半身证件照要求")
    except Exception:
        # 人脸组件不可用时仍执行尺寸、比例和彩色检查，不把证件照送入OCR。
        pass
    return reasons
