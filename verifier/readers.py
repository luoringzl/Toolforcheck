from __future__ import annotations

import io
import re
from pathlib import Path

import fitz
from docx import Document
from PIL import Image, ImageOps

from .config import AppConfig
from .models import Material
from .ocr import LocalTesseractOCR
from .quality import assess_id_image


def classify_document(path: Path) -> str:
    n = path.stem.lower()
    rules = [
        ("身份证", ("身份证", "idcard", "id_card")),
        ("毕业证", ("毕业证", "学历证", "毕业证明")),
        ("学位证", ("学位证",)),
        ("学历认证", ("学信", "学历认证", "认证报告")),
        ("劳动合同", ("劳动合同", "聘用合同", "合同")),
        ("离职证明", ("离职", "解除劳动", "终止劳动")),
        ("工作证明", ("工作证明", "任职证明", "在职证明")),
        ("简历", ("简历", "resume", "cv")),
    ]
    for label, keys in rules:
        if any(k in n for k in keys):
            return label
    return "其他材料"


def _docx_pages(path: Path) -> list[str]:
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text.strip() for cell in row.cells))
    for section in doc.sections:
        parts.extend(p.text for p in section.header.paragraphs if p.text.strip())
        parts.extend(p.text for p in section.footer.paragraphs if p.text.strip())
    return ["\n".join(parts)]


def _render_pdf_page(page: fitz.Page, dpi: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def read_material(person: str, path: Path, cfg: AppConfig, ocr: LocalTesseractOCR) -> Material:
    kind = classify_document(path)
    m = Material(person=person, path=path, document_type=kind)
    try:
        suffix = path.suffix.lower()
        if suffix == ".docx":
            m.text_pages = _docx_pages(path)
        elif suffix == ".pdf":
            doc = fitz.open(path)
            for page in doc:
                text = page.get_text("text").strip()
                if len(re.sub(r"\s", "", text)) >= 30:
                    m.text_pages.append(text)
                else:
                    image = _render_pdf_page(page, cfg.image_dpi)
                    if kind == "身份证":
                        reasons = assess_id_image(image, cfg.quality, ocr.command, ocr.environment)
                        m.quality_reasons.extend(f"第{page.number + 1}页：{r}" for r in reasons)
                    m.text_pages.append(ocr.recognize(image) if not m.quality_reasons else "")
        else:
            image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            if kind == "身份证":
                m.quality_reasons = assess_id_image(image, cfg.quality, ocr.command, ocr.environment)
            if not m.quality_reasons:
                m.text_pages = [ocr.recognize(image)]
        if m.quality_reasons:
            m.quality_status = "退回"
        if not any(x.strip() for x in m.text_pages) and not m.quality_reasons:
            m.errors.append("未提取到可用文字")
    except Exception as exc:
        m.errors.append(str(exc))
    return m
