from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import PersonResult

HEAD_FILL = PatternFill("solid", fgColor="1F4E78")
HEAD_FONT = Font(color="FFFFFF", bold=True)
STATUS_FILL = {
    "通过": "C6EFCE", "一致": "C6EFCE", "待复核": "FFEB9C",
    "齐全": "C6EFCE", "豁免": "DDEBF7", "已填写": "C6EFCE",
    "人工复核": "FFEB9C", "无法核对": "FFEB9C", "缺少信息": "FFEB9C",
    "退回": "FFC7CE", "不一致": "FFC7CE", "不通过": "FFC7CE",
    "缺少材料": "FFC7CE", "缺少或不一致": "FFC7CE", "材料不采用": "E7E6E6",
    "不适用": "E7E6E6",
}


def _sheet(wb: Workbook, title: str, headers: list[str]):
    ws = wb.create_sheet(title)
    ws.append(headers)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    for c in ws[1]:
        c.fill, c.font, c.alignment = HEAD_FILL, HEAD_FONT, Alignment(horizontal="center")
    return ws


def _finish(ws):
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if str(cell.value) in STATUS_FILL:
                cell.fill = PatternFill("solid", fgColor=STATUS_FILL[str(cell.value)])
    for col in range(1, ws.max_column + 1):
        values = [str(ws.cell(r, col).value or "") for r in range(1, min(ws.max_row, 100) + 1)]
        ws.column_dimensions[get_column_letter(col)].width = min(55, max(12, max(map(len, values), default=12) + 2))


def write_report(results: list[PersonResult], output: Path) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    total = _sheet(wb, "人员核验总表", ["人员", "总体结果", "材料数", "退回数", "不一致数", "待复核数"])
    detail = _sheet(wb, "字段差异明细", ["人员", "类别", "字段", "状态", "说明", "字段值", "来源文件与页码"])
    review = _sheet(wb, "人工复核清单", ["人员", "类别", "字段", "状态", "复核原因", "识别值", "来源文件与页码"])
    evidence_sheet = _sheet(wb, "字段识别依据", ["人员", "材料类型", "字段", "识别值", "OCR置信度", "来源文件", "页码"])
    complete = _sheet(wb, "材料完整性审核", ["人员", "材料类型", "状态", "判断依据", "数量或结果", "来源"])
    works = _sheet(wb, "工作经历明细", ["人员", "企业名称", "从事职业", "开始时间", "结束时间", "工作月数", "证明人姓名", "证明人电话", "企业名称状态", "企业名称说明", "经营范围", "来源"])
    mats = _sheet(wb, "材料清单", ["人员", "文件", "材料类型", "是否核验依据", "质量状态", "质量原因", "处理异常"])
    rejects = _sheet(wb, "退回清单", ["人员", "字段/材料", "退回原因", "来源"])
    for r in results:
        s = r.summary
        total.append([r.person, s["总体结果"], s["材料数"], s["退回数"], s["不一致数"], s["待复核数"]])
        for f in r.findings:
            detail.append([f.person, f.category, f.field, f.status, f.message, f.values, f.sources])
            if f.status in {"待复核", "人工复核", "无法核对", "缺少信息"}:
                review.append([f.person, f.category, f.field, f.status, f.message, f.values, f.sources])
            if f.category == "材料完整性":
                complete.append([f.person, f.field, f.status, f.message, f.values, f.sources])
            if f.status == "退回":
                rejects.append([f.person, f.field, f.message, f.sources])
        for w in r.work_records:
            works.append([w.person, w.company, w.occupation, w.start, w.end, w.duration_months, w.witness_name, w.witness_phone, w.company_status, w.company_message, w.business_scope, w.source])
        for m in r.materials:
            mats.append([m.person, m.path.name, m.document_type, "是" if m.selected_as_basis else "否", m.quality_status, "；".join(m.quality_reasons), "；".join(m.errors)])
            for e in m.evidences:
                confidence = "" if e.confidence is None else f"{e.confidence:.0%}"
                evidence_sheet.append([e.person, e.document_type, e.field, e.normalized_value, confidence, e.file, e.page])
    for ws in wb.worksheets:
        _finish(ws)
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
