from __future__ import annotations

import re

from .models import Evidence, Material, WorkRecord
from .normalize import normalize_company, normalize_date, normalize_id, normalize_name

DATE = r"(?:19\d{2}|20\d{2})[年./\-]\d{1,2}(?:[月./\-]\d{1,2}日?)?"


def _first(patterns: list[str], text: str, flags: int = 0) -> str:
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m.group(1).strip(" ：:\t，,。")
    return ""


def extract_material(material: Material) -> tuple[list[Evidence], list[WorkRecord]]:
    evidences: list[Evidence] = []
    work: list[WorkRecord] = []
    for page_no, text in enumerate(material.text_pages, 1):
        if not text.strip():
            continue
        candidates = {
            "姓名": (_first([r"姓名\s*[：:]?\s*([\u4e00-\u9fff·]{2,8})", r"姓\s*名\s*([\u4e00-\u9fff·]{2,8})"], text), normalize_name),
            "身份证号": (_first([r"(?:公民身份号码|身份证(?:号码|号)?)\s*[：:]?\s*([0-9Xx\s]{18,24})", r"(?<!\d)([1-9]\d{16}[0-9Xx])(?!\d)"], text), normalize_id),
            "出生日期": (_first([rf"(?:出生日期|出生年月|出生)\s*[：:]?\s*({DATE})"], text), normalize_date),
            "毕业院校": (_first([r"(?:毕业院校|毕业学校|院校名称|学校名称)\s*[：:]?\s*([^\n\t，,。]{2,40}(?:大学|学院|学校))", r"([\u4e00-\u9fff]{2,30}(?:大学|学院))"], text), lambda x: x.strip()),
            "毕业时间": (_first([rf"(?:毕业时间|毕业日期|授予日期|发证日期)\s*[：:]?\s*({DATE})"], text), normalize_date),
            "毕业证编码": (_first([r"(?:毕业证书编号|学历证书编号|证书编号)\s*[：:]?\s*([A-Za-z0-9\-]{6,40})"], text), lambda x: re.sub(r"\s", "", x).upper()),
            "学位证编码": (_first([r"(?:学位证书编号|学位证编号)\s*[：:]?\s*([A-Za-z0-9\-]{6,40})"], text), lambda x: re.sub(r"\s", "", x).upper()),
        }
        for field, (raw, normalizer) in candidates.items():
            if raw:
                evidences.append(Evidence(material.person, material.path.name, page_no, material.document_type, field, raw, normalizer(raw)))

        company_patterns = [
            r"(?:企业名称|单位名称|公司名称|用人单位|甲方|任职单位|工作单位)\s*[：:]?\s*([^\n\t，,。；;]{2,60})",
        ]
        companies = []
        for p in company_patterns:
            companies.extend(m.group(1).strip() for m in re.finditer(p, text))
        ranges = list(re.finditer(rf"({DATE})\s*(?:至|到|—|–|-|~|～)\s*({DATE}|至今)", text))
        for idx, rm in enumerate(ranges):
            company = companies[min(idx, len(companies) - 1)] if companies else ""
            if company:
                work.append(WorkRecord(material.person, normalize_company(company), normalize_date(rm.group(1)), normalize_date(rm.group(2)) if rm.group(2) != "至今" else "至今", None, f"{material.path.name} 第{page_no}页"))
    material.evidences = evidences
    return evidences, work
