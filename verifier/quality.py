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
