from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageOps


def _extract_rapid_text(result: Any, minimum_score: float = 0.30) -> str:
    """兼容 RapidOCR 3.x 输出对象及旧版列表输出。"""
    if result is None:
        return ""

    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if texts is not None:
        values = []
        scores = list(scores) if scores is not None else [1.0] * len(texts)
        for text, score in zip(texts, scores):
            value = str(text or "").strip()
            if value and (score is None or float(score) >= minimum_score):
                values.append(value)
        return "\n".join(values)

    payload = result[0] if isinstance(result, tuple) and result else result
    if isinstance(payload, list):
        values = []
        for item in payload:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = item[1]
            score = item[2] if len(item) > 2 else 1.0
            value = str(text or "").strip()
            if value and (score is None or float(score) >= minimum_score):
                values.append(value)
        return "\n".join(values)
    return ""


def _rapid_confidence(result: Any, minimum_score: float = 0.30) -> float | None:
    scores = getattr(result, "scores", None)
    if scores is not None:
        values = [float(score) for score in scores if score is not None and float(score) >= minimum_score]
        return sum(values) / len(values) if values else None
    payload = result[0] if isinstance(result, tuple) and result else result
    if isinstance(payload, list):
        values = [
            float(item[2]) for item in payload
            if isinstance(item, (list, tuple)) and len(item) > 2
            and item[2] is not None and float(item[2]) >= minimum_score
        ]
        return sum(values) / len(values) if values else None
    return None


class LocalTesseractOCR:
    """兼容旧调用名称的纯离线RapidOCR引擎。"""

    def __init__(self, language: str = "chi_sim+eng"):
        self.language = language
        self.rapid = None
        self.rapid_error = ""
        self.last_confidence: float | None = None
        try:
            from rapidocr import RapidOCR

            self.rapid = RapidOCR()
        except Exception as exc:
            # 安装包若发生模型异常仍允许使用Tesseract，错误会在两者均失败时报告。
            self.rapid_error = str(exc)

    def available(self) -> bool:
        return self.rapid is not None

    def _recognize_rapid(self, image: Image.Image) -> str:
        if self.rapid is None:
            return ""
        array = np.asarray(image)
        result = self.rapid(array)
        self.last_confidence = _rapid_confidence(result)
        return _extract_rapid_text(result)

    def recognize(self, image: Image.Image) -> str:
        image = ImageOps.exif_transpose(image).convert("RGB")
        self.last_confidence = None
        try:
            rapid_text = self._recognize_rapid(image)
            if len("".join(rapid_text.split())) >= 2:
                return rapid_text
        except Exception as exc:
            raise RuntimeError(f"离线OCR未能提取文字（RapidOCR: {exc}）") from exc
        return ""
