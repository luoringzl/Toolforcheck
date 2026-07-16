from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


class LocalTesseractOCR:
    def __init__(self, language: str = "chi_sim+eng"):
        bundled_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        bundled_cmd = bundled_root / "tesseract" / "tesseract.exe"
        self.command = os.environ.get(
            "TESSERACT_CMD", str(bundled_cmd) if bundled_cmd.exists() else "tesseract"
        )
        tessdata = bundled_root / "tesseract" / "tessdata"
        self.environment = os.environ.copy()
        if bundled_cmd.exists():
            # Always override stale machine-level values for the bundled OCR.
            self.environment["TESSDATA_PREFIX"] = str(tessdata)
        self.creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.language = language

    def available(self) -> bool:
        try:
            if Path(self.command).name.lower() == "tesseract.exe":
                tessdata = Path(self.environment.get("TESSDATA_PREFIX", ""))
                if not all((tessdata / name).exists() for name in ("chi_sim.traineddata", "eng.traineddata")):
                    return False
            return subprocess.run(
                [self.command, "--version"], capture_output=True, timeout=10,
                env=self.environment, creationflags=self.creationflags
            ).returncode == 0
        except Exception:
            return False

    def recognize(self, image: Image.Image) -> str:
        image = ImageOps.exif_transpose(image).convert("RGB")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "page.png"
            image.save(path)
            langs = self.language
            cmd = [self.command, str(path), "stdout", "-l", langs, "--psm", "6"]
            cp = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180,
                env=self.environment, creationflags=self.creationflags
            )
            if cp.returncode != 0 and "chi_sim" in langs:
                cp = subprocess.run(
                    [self.command, str(path), "stdout", "-l", "eng", "--psm", "6"],
                    capture_output=True, text=True, timeout=180,
                    env=self.environment, creationflags=self.creationflags
                )
            if cp.returncode != 0:
                raise RuntimeError(cp.stderr.strip() or "本地OCR执行失败")
            return cp.stdout.strip()
