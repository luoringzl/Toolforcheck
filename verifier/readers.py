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
        ("申报表", ("福建省职业技能等级认定申报表", "认定申报表", "申报表", "报名表")),
        ("证件照", ("证件照", "登记照", "一寸照", "二寸照", "照片", "photo")),
        ("身份证", ("身份证", "idcard", "id_card")),
        ("学历证明", ("毕业证", "学历证", "毕业证明", "初中毕业", "高中毕业", "中职毕业", "高职毕业", "本科毕业", "研究生毕业")),
        ("学位证", ("学位证",)),
        ("学信网学籍证明", ("学信", "学籍证明", "学籍在线验证", "学历在线验证", "教育部学籍")),
        ("工作年限承诺书", ("工作年限承诺", "年限承诺", "承诺函", "承诺书")),
        ("企业信息截图", ("企业信息", "工商信息", "经营范围", "企查查", "天眼查", "爱企查", "国家企业信用")),
        ("劳动合同", ("劳动合同", "聘用合同", "合同")),
        ("离职证明", ("离职", "解除劳动", "终止劳动")),
        ("工作证明", ("工作证明", "任职证明", "在职证明")),
        ("简历", ("简历", "resume", "cv")),
    ]
    for label, keys in rules:
        if any(k in n for k in keys):
            return label
    return "其他材料"


def refine_document_type(kind: str, text: str) -> str:
    compact = re.sub(r"\s", "", text)
    signatures = [
        ("申报表", ("福建省职业技能等级认定申报表", "职业技能等级认定申报表")),
        ("身份证", ("中华人民共和国居民身份证", "公民身份号码", "签发机关")),
        ("学信网学籍证明", ("学信网", "学籍在线验证报告", "学历证书电子注册备案表")),
        ("工作年限承诺书", ("工作年限承诺书", "工作年限承诺函")),
        ("企业信息截图", ("统一社会信用代码", "经营范围", "登记状态")),
        ("工作证明", ("工作证明", "兹证明", "在我单位工作")),
        ("学历证明", ("毕业证书", "修业期满", "准予毕业")),
    ]
    for label, keys in signatures:
        if any(k in compact for k in keys):
            return label
    return kind


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
        m.document_type = refine_document_type(m.document_type, "\n".join(m.text_pages))
        if not any(x.strip() for x in m.text_pages) and not m.quality_reasons:
            m.errors.append("未提取到可用文字")
    except Exception as exc:
        m.errors.append(str(exc))
    return m
