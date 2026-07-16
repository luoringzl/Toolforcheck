from __future__ import annotations

import re

from .idcard import validate_cn_id
from .models import Evidence, Material, WorkRecord
from .normalize import normalize_company, normalize_date, normalize_id, normalize_name

ARABIC_DATE = r"(?:19\d{2}|20\d{2})[年./\-]\d{1,2}(?:[月./\-]\d{1,2}日?)?"
CHINESE_DATE = r"[〇零一二三四五六七八九]{4}年[一二三四五六七八九十]{1,3}月(?:[一二三四五六七八九十]{1,3}日)?"
DATE = rf"(?:{ARABIC_DATE}|{CHINESE_DATE})"


def _first(patterns: list[str], text: str, flags: int = 0) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip(" ：:\t，,。")
    return ""


def _best_id(text: str) -> str:
    labelled = re.findall(r"(?:公民身份号码|身份证(?:号码|号)?)\s*[：:]?\s*([0-9Xx\s]{18,28})", text)
    general = re.findall(r"(?<!\d)([1-9]\d{16}[0-9Xx])(?!\d)", re.sub(r"\s", "", text))
    candidates = []
    for raw in labelled + general:
        number = normalize_id(raw)
        if len(number) == 18 and number not in candidates:
            candidates.append(number)
    valid = [number for number in candidates if validate_cn_id(number)[0]]
    return (valid or candidates or [""])[0]


def _all_dates(text: str) -> list[str]:
    return [normalize_date(x) for x in re.findall(DATE, text)]


def _education_level(text: str) -> str:
    levels = ["研究生", "硕士", "博士", "本科", "高职", "大专", "专科", "中职", "中专", "高中", "初中"]
    for level in levels:
        if level in text:
            return {"硕士":"研究生", "博士":"研究生", "专科":"大专", "中专":"中职"}.get(level, level)
    return ""


def _work_records(text: str, material: Material, page_no: int) -> list[WorkRecord]:
    companies = [m.group(1).strip() for m in re.finditer(
        r"(?:企业名称|单位名称|公司名称|用人单位|甲方|任职单位|工作单位)\s*[：:]?\s*([^\n\t，,。；;]{2,80})", text
    )]
    occupations = [m.group(1).strip() for m in re.finditer(
        r"(?:从事职业|职业工种|工作岗位|岗位|职务)\s*[：:]?\s*([^\n\t，,。；;]{1,30})", text
    )]
    scopes = [m.group(1).strip() for m in re.finditer(
        r"经营范围\s*[：:]?\s*([^\n]{4,500})", text
    )]
    ranges = list(re.finditer(rf"({DATE})\s*(?:至|到|—|–|-|~|～)\s*({DATE}|至今)", text))
    records: list[WorkRecord] = []
    for index, date_match in enumerate(ranges):
        company = companies[min(index, len(companies) - 1)] if companies else ""
        if not company:
            continue
        end_raw = date_match.group(2)
        records.append(WorkRecord(
            person=material.person,
            company=normalize_company(company),
            start=normalize_date(date_match.group(1)),
            end="至今" if end_raw == "至今" else normalize_date(end_raw),
            duration_months=None,
            source=f"{material.path.name} 第{page_no}页",
            occupation=occupations[min(index, len(occupations) - 1)] if occupations else "",
            business_scope=scopes[min(index, len(scopes) - 1)] if scopes else "",
            source_type=material.document_type,
        ))
    return records


def extract_material(material: Material) -> tuple[list[Evidence], list[WorkRecord]]:
    evidences: list[Evidence] = []
    work: list[WorkRecord] = []
    for page_no, text in enumerate(material.text_pages, 1):
        if not text.strip():
            continue
        id_number = _best_id(text)
        candidates = {
            "姓名": (_first([r"姓名\s*[：:]?\s*([\u4e00-\u9fff·]{2,8})", r"姓\s*名\s*([\u4e00-\u9fff·]{2,8})"], text), normalize_name),
            "性别": (_first([r"性别\s*[：:]?\s*([男女])"], text), lambda x: x),
            "身份证号": (id_number, normalize_id),
            "出生日期": (_first([rf"(?:出生日期|出生年月|出生)\s*[：:]?\s*({DATE})"], text), normalize_date),
            "毕业院校": (_first([r"(?:毕业院校|毕业学校|院校名称|学校名称)\s*[：:]?\s*([^\n\t，,。]{2,50}(?:大学|学院|学校))", r"([\u4e00-\u9fff]{2,30}(?:大学|学院|学校))"], text), lambda x: x.strip()),
            "毕业证编码": (_first([r"(?:毕业证书编号|学历证书编号|证书编号)\s*[：:]?\s*([A-Za-z0-9\-]{6,40})"], text), lambda x: re.sub(r"\s", "", x).upper()),
            "学位证编码": (_first([r"(?:学位证书编号|学位证编号)\s*[：:]?\s*([A-Za-z0-9\-]{6,40})"], text), lambda x: re.sub(r"\s", "", x).upper()),
            "学历层次": (_education_level(text), lambda x: x),
            "学籍状态": (_first([r"(?:学籍状态|学习形式|状态)\s*[：:]?\s*(在籍|在校|毕业|结业)"], text), lambda x: x),
            "身份证有效期至": (_first([rf"(?:有效期限|有效期)\s*[：:]?\s*(?:{DATE}\s*[-至]\s*)?({DATE}|长期)"], text), normalize_date),
            "从事职业": (_first([r"(?:从事职业|职业工种|申报职业|职业名称)\s*[：:]?\s*([^\n\t，,。；;]{1,30})"], text), lambda x: x.strip()),
            "企业名称": (_first([r"(?:企业名称|单位名称|公司名称|用人单位|任职单位|工作单位)\s*[：:]?\s*([^\n\t，,。；;]{2,80})"], text), normalize_company),
            "经营范围": (_first([r"经营范围\s*[：:]?\s*([^\n]{4,500})"], text), lambda x: x.strip()),
        }
        # 普通学历证明以证书页面最后出现的日期作为右下角落款日期。
        dates = _all_dates(text)
        if material.document_type == "学历证明" and dates:
            candidates["毕业时间"] = (dates[-1], normalize_date)
        else:
            candidates["毕业时间"] = (_first([rf"(?:毕业时间|毕业日期|授予日期|发证日期)\s*[：:]?\s*({DATE})"], text), normalize_date)

        for field, (raw, normalizer) in candidates.items():
            if raw:
                evidences.append(Evidence(
                    material.person, material.path.name, page_no,
                    material.document_type, field, raw, normalizer(raw)
                ))
        work.extend(_work_records(text, material, page_no))
    material.evidences = evidences
    return evidences, work
