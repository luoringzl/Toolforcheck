from __future__ import annotations

from pathlib import Path
from typing import Callable

from .company import CompanyRegistry
from .config import AppConfig
from .extract import extract_material
from .models import PersonResult
from .ocr import LocalTesseractOCR
from .readers import read_material
from .report import write_report
from .rules import evaluate


def run(input_dir: Path, output: Path, registry_path: str | None = None, cfg: AppConfig | None = None, progress: Callable[[str], None] | None = None) -> list[PersonResult]:
    cfg = cfg or AppConfig()
    log = progress or (lambda _: None)
    ocr = LocalTesseractOCR(cfg.ocr_language)
    if not ocr.available():
        raise RuntimeError("未检测到本地 Tesseract OCR，请安装后重试")
    registry = CompanyRegistry(registry_path)
    people = sorted(p for p in input_dir.iterdir() if p.is_dir())
    if not people:
        raise ValueError("所选文件夹中没有人员子文件夹")
    results: list[PersonResult] = []
    for idx, folder in enumerate(people, 1):
        log(f"[{idx}/{len(people)}] 正在处理：{folder.name}")
        paths = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in cfg.supported_extensions)
        materials = [read_material(folder.name, p, cfg, ocr) for p in paths]
        evidences, works = [], []
        for m in materials:
            e, w = extract_material(m)
            evidences.extend(e); works.extend(w)
        results.append(evaluate(folder.name, materials, evidences, works, registry, cfg))
    write_report(results, output)
    log(f"完成：{output}")
    return results
