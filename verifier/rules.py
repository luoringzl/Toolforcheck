from __future__ import annotations

from collections import defaultdict

from .company import CompanyRegistry
from .idcard import birthday_from_id, validate_cn_id
from .models import Evidence, Finding, Material, PersonResult, WorkRecord
from .normalize import duration_months


def _compare_field(person: str, field: str, values: list[Evidence]) -> Finding:
    grouped: dict[str, list[Evidence]] = defaultdict(list)
    for e in values:
        grouped[e.normalized_value].append(e)
    sources = "; ".join(f"{e.file} 第{e.page}页={e.raw_value}" for e in values)
    if len(grouped) == 1:
        return Finding(person, "字段一致性", field, "一致", "各材料信息一致", next(iter(grouped)), sources)
    return Finding(person, "字段一致性", field, "不一致", f"{field}在不同材料中不一致", " | ".join(grouped), sources)


def evaluate(person: str, materials: list[Material], evidences: list[Evidence], work: list[WorkRecord], registry: CompanyRegistry) -> PersonResult:
    result = PersonResult(person=person, materials=materials, work_records=work)
    for m in materials:
        if m.quality_status == "退回":
            reason = "；".join(m.quality_reasons)
            result.findings.append(Finding(person, "材料质量", "身份证材料", "退回", f"该材料不符合规范，请重新提交。原因：{reason}", sources=m.path.name))
        for error in m.errors:
            result.findings.append(Finding(person, "处理异常", "文件读取", "待复核", error, sources=m.path.name))

    by_field: dict[str, list[Evidence]] = defaultdict(list)
    for e in evidences:
        by_field[e.field].append(e)
    for field, vals in by_field.items():
        result.findings.append(_compare_field(person, field, vals))

    ids = by_field.get("身份证号", [])
    for e in ids:
        ok, reasons = validate_cn_id(e.normalized_value)
        if not ok:
            result.findings.append(Finding(person, "身份逻辑", "身份证号", "不一致", "；".join(reasons), e.normalized_value, f"{e.file} 第{e.page}页"))
        else:
            birthdays = {x.normalized_value for x in by_field.get("出生日期", [])}
            if birthdays and birthday_from_id(e.normalized_value) not in birthdays:
                result.findings.append(Finding(person, "身份逻辑", "出生日期", "不一致", "材料中的出生日期与身份证号码内日期不一致", birthday_from_id(e.normalized_value), e.file))

    for wr in work:
        status, message = registry.validate(wr.company)
        wr.company_status, wr.company_message = status, message
        wr.duration_months = None if wr.end == "至今" else duration_months(wr.start, wr.end)
        if status != "通过":
            result.findings.append(Finding(person, "企业名称", "企业全称", status, message, wr.company, wr.source))
        if wr.end != "至今" and wr.duration_months is None:
            result.findings.append(Finding(person, "时间逻辑", "工作起止时间", "不一致", "工作结束时间早于开始时间或日期无法识别", f"{wr.start}—{wr.end}", wr.source))

    statuses = [f.status for f in result.findings]
    overall = "通过"
    if any(x in ("退回", "不一致") for x in statuses):
        overall = "不通过"
    elif any(x == "待复核" for x in statuses):
        overall = "待复核"
    result.summary = {
        "总体结果": overall,
        "材料数": len(materials),
        "退回数": sum(f.status == "退回" for f in result.findings),
        "不一致数": sum(f.status == "不一致" for f in result.findings),
        "待复核数": sum(f.status == "待复核" for f in result.findings),
    }
    return result

