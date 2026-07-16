from __future__ import annotations

import subprocess
import tempfile
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


def detect_rotation(image: Image.Image, tesseract_cmd: str, environment: dict[str, str] | None = None) -> float | None:
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = Path(f.name)
        image.save(tmp)
        cp = subprocess.run(
            [tesseract_cmd, str(tmp), "stdout", "--psm", "0"],
            capture_output=True, text=True, timeout=20, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        for line in (cp.stdout or "").splitlines():
            if line.startswith("Rotate:"):
                return float(line.split(":", 1)[1].strip())
    except Exception:
        return None
    finally:
        if 'tmp' in locals():
            tmp.unlink(missing_ok=True)
    return None


def assess_id_image(image: Image.Image, cfg: QualityConfig, tesseract_cmd: str, environment: dict[str, str] | None = None) -> list[str]:
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
    rotation = detect_rotation(image, tesseract_cmd, environment)
    if rotation is not None and min(rotation, abs(360 - rotation)) > cfg.severe_rotation_degrees:
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
