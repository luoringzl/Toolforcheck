from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
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


class LocalTesseractOCR:
    """离线双引擎OCR：RapidOCR主识别，Tesseract兜底及方向检测。"""

    def __init__(self, language: str = "chi_sim+eng"):
        bundled_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        bundled_cmd = bundled_root / "tesseract" / "tesseract.exe"
        self.command = os.environ.get(
            "TESSERACT_CMD", str(bundled_cmd) if bundled_cmd.exists() else "tesseract"
        )
        tessdata = bundled_root / "tesseract" / "tessdata"
        self.environment = os.environ.copy()
        if bundled_cmd.exists():
            self.environment["TESSDATA_PREFIX"] = str(tessdata)
        self.creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.language = language
        self.rapid = None
        self.rapid_error = ""
        try:
            from rapidocr import RapidOCR

            self.rapid = RapidOCR()
        except Exception as exc:
            # 安装包若发生模型异常仍允许使用Tesseract，错误会在两者均失败时报告。
            self.rapid_error = str(exc)

    def _tesseract_available(self) -> bool:
        try:
            if Path(self.command).name.lower() == "tesseract.exe":
                tessdata = Path(self.environment.get("TESSDATA_PREFIX", ""))
                if not all(
                    (tessdata / name).exists()
                    for name in ("chi_sim.traineddata", "eng.traineddata")
                ):
                    return False
            return (
                subprocess.run(
                    [self.command, "--version"],
                    capture_output=True,
                    timeout=10,
                    env=self.environment,
                    creationflags=self.creationflags,
                ).returncode
                == 0
            )
        except Exception:
            return False

    def available(self) -> bool:
        return self.rapid is not None or self._tesseract_available()

    def _recognize_rapid(self, image: Image.Image) -> str:
        if self.rapid is None:
            return ""
        array = np.asarray(image)
        result = self.rapid(array)
        return _extract_rapid_text(result)

    def _recognize_tesseract(self, image: Image.Image) -> str:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "page.png"
            image.save(path)

            def execute(language: str, psm: str):
                return subprocess.run(
                    [
                        self.command,
                        str(path),
                        "stdout",
                        "-l",
                        language,
                        "--psm",
                        psm,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    env=self.environment,
                    creationflags=self.creationflags,
                )

            cp = execute(self.language, "6")
            if cp.returncode != 0 and "chi_sim" in self.language:
                cp = execute("eng", "6")
            if cp.returncode != 0:
                raise RuntimeError((cp.stderr or "").strip() or "本地OCR执行失败")
            primary = (cp.stdout or "").strip()
            sparse_cp = execute(self.language, "11")
            sparse = (
                (sparse_cp.stdout or "").strip()
                if sparse_cp.returncode == 0
                else ""
            )
            return "\n".join(part for part in (primary, sparse) if part)

    def recognize(self, image: Image.Image) -> str:
        image = ImageOps.exif_transpose(image).convert("RGB")
        errors = []
        try:
            rapid_text = self._recognize_rapid(image)
            if len("".join(rapid_text.split())) >= 2:
                return rapid_text
        except Exception as exc:
            errors.append(f"RapidOCR: {exc}")

        try:
            fallback = self._recognize_tesseract(image)
            if fallback.strip():
                return fallback
        except Exception as exc:
            errors.append(f"Tesseract: {exc}")

        detail = "；".join(errors)
        if detail:
            raise RuntimeError(f"离线OCR未能提取文字（{detail}）")
        return ""
