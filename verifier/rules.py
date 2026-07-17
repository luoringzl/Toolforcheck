from __future__ import annotations

from collections import defaultdict
from datetime import date
import re

from .company import CompanyRegistry
from .config import AppConfig
from .idcard import birthday_from_id, gender_from_id, validate_cn_id
from .models import Evidence, Finding, Material, PersonResult, WorkRecord
from .normalize import duration_months, format_year_month, month_index, normalize_company

HIGHER_EDUCATION = {"大专", "高职", "本科", "研究生"}
IN_SCHOOL = {"在籍", "在校"}
CHSI_TYPES = {"学信网学籍证明", "学信网学历证明", "学信网学位证明"}
LEVEL_RANK = {"初中": 1, "高中": 2, "中职": 2, "大专": 3, "高职": 3, "本科": 4, "研究生": 5}
KEY_OCR_FIELDS = {"姓名", "身份证号", "毕业院校", "毕业时间", "毕业证编码", "企业名称"}


def _add(result: PersonResult, category: str, field: str, status: str, message: str, values: str = "", sources: str = "") -> None:
    result.findings.append(Finding(result.person, category, field, status, message, values, sources))


def _by_field(evidences: list[Evidence]) -> dict[str, list[Evidence]]:
    grouped: dict[str, list[Evidence]] = defaultdict(list)
    for evidence in evidences:
        grouped[evidence.field].append(evidence)
    return grouped


def _material_evidence(material: Material, field: str) -> list[Evidence]:
    return [e for e in material.evidences if e.field == field]


def _usable_material(material: Material) -> bool:
    return material.quality_status == "合格" and not material.errors


def _id_expiry(material: Material) -> int:
    expiry = _material_evidence(material, "身份证有效期至")
    if not expiry:
        return 0
    value = expiry[0].normalized_value
    if value == "长期":
        return 999999
    return month_index(value) or 0


def _select_valid_id(materials: list[Material], result: PersonResult) -> Material | None:
    id_materials = [m for m in materials if m.document_type == "身份证"]
    front_candidates: list[Material] = []
    back_candidates: list[Material] = []
    now_index = date.today().year * 12 + date.today().month - 1
    for material in id_materials:
        ids = _material_evidence(material, "身份证号")
        expiry = _id_expiry(material)
        valid_number = bool(ids and validate_cn_id(ids[0].normalized_value)[0])
        unexpired = expiry == 999999 or expiry >= now_index
        if material.quality_status == "合格" and valid_number:
            front_candidates.append(material)
        if material.quality_status == "合格" and expiry and unexpired:
            back_candidates.append(material)
        if material.quality_status != "合格":
            reasons = list(material.quality_reasons)
            _add(result, "材料质量", "身份证", "材料不采用", "该份身份证不作为核验依据：" + "；".join(reasons), sources=material.path.name)
        elif expiry and not unexpired:
            _add(result, "材料质量", "身份证", "材料不采用", "该份身份证已过有效期，不作为核验依据", sources=material.path.name)
    valid_numbers = {
        e.normalized_value
        for material in front_candidates
        for e in _material_evidence(material, "身份证号")
        if validate_cn_id(e.normalized_value)[0]
    }
    if len(valid_numbers) > 1:
        _add(result, "身份信息核对", "身份证号", "退回", "多份合格身份证识别出不同身份证号码，不能自动择优，请人工核实", "；".join(sorted(valid_numbers)))
        return None
    if not front_candidates or not back_candidates:
        if id_materials:
            missing = []
            if not front_candidates: missing.append("未找到身份证号可可靠识别且校验通过的清晰正面")
            if not back_candidates: missing.append("未找到在有效期内的清晰身份证背面")
            _add(result, "材料质量", "身份证", "退回", "已提交身份证中没有可组合成一套的合格正反面，请重新提交。" + "；".join(missing))
        return None
    def front_score(material: Material) -> tuple[int, float, int]:
        fields = {e.field for e in material.evidences}
        confidence = material.ocr_confidence if material.ocr_confidence is not None else 1.0
        return (sum(field in fields for field in ("姓名", "身份证号", "出生日期", "性别")), confidence, -len(material.errors))

    selected_front = max(front_candidates, key=front_score)
    selected_back = max(back_candidates, key=_id_expiry)
    selected_front.selected_as_basis = True
    selected_back.selected_as_basis = True
    sources = selected_front.path.name if selected_front is selected_back else f"{selected_front.path.name}；{selected_back.path.name}"
    _add(result, "材料择优", "身份证", "通过", "已选用清晰完整的正面及在有效期内的背面作为核验依据", sources=sources)
    return selected_front


def _apply_review_preset(
    result: PersonResult,
    level: str,
    student_status: str,
    graduation: str,
    form_work: list[WorkRecord],
    cfg: AppConfig,
) -> tuple[str, str, str]:
    """用人工预设补充自动判断，并把采用情况写入审核报告。"""
    preset = cfg.review_preset
    if preset.is_college_student and preset.is_graduated:
        _add(result, "人工预设", "人员身份", "不一致", "高校在校生与已毕业不能同时选择；本次仍采用材料自动判断")
    elif preset.is_college_student:
        student_status = "在籍"
        _add(result, "人工预设", "人员身份", "已采用", "本批次人工指定为高校在校生；学历证明按在籍规则审核")
    elif preset.is_graduated:
        student_status = "毕业"
        _add(result, "人工预设", "人员身份", "已采用", "本批次人工指定为已毕业；毕业证及工作经历按已毕业规则审核")
    if preset.is_working:
        _add(result, "人工预设", "人员身份", "已采用", "本批次人工指定为已工作；工作相关材料按有工作经历规则审核")

    if preset.education_level:
        level = preset.education_level
        _add(result, "人工预设", "最高学历", "已采用", "最高学历采用操作面板人工预设", level)

    actual_count = len(form_work)
    if preset.work_history:
        expected = preset.work_history
        matched = (
            (expected == "无" and actual_count == 0)
            or (expected == "1份" and actual_count == 1)
            or (expected == "2份及以上" and actual_count >= 2)
        )
        _add(
            result,
            "人工预设",
            "工作经历",
            "一致" if matched else "不一致",
            "操作面板预设与申报表实际读取到的工作经历段数核对",
            f"预设={expected}；申报表={actual_count}段",
        )
    if preset.is_working and actual_count == 0:
        _add(result, "申报表填写核验", "工作经历", "缺少信息", "人工指定为已工作，但申报表未读取到完整工作经历")
    return level, student_status, graduation


def _required_materials(
    result: PersonResult,
    materials: list[Material],
    form_work: list[WorkRecord],
    level: str,
    student_status: str,
    cfg: AppConfig,
) -> None:
    types = defaultdict(list)
    for material in materials:
        types[material.document_type].append(material)
    preset = cfg.review_preset
    forced = set(preset.forced_required_materials)

    def require(kind: str, condition: bool, reason: str, quantity: int = 1) -> None:
        if kind in forced:
            condition = True
            reason = f"操作面板已勾选为本批次强制材料；{reason}"
        qualified = [m for m in types[kind] if _usable_material(m)]
        if kind == "身份证":
            # 身份证必须有可组合使用的清晰正反面；选择结果由_select_valid_id标记。
            qualified = [m for m in qualified if m.selected_as_basis]
        if condition and len(qualified) < quantity:
            _add(result, "材料完整性", kind, "缺少材料", f"缺少合格的{kind}。触发条件：{reason}", f"应有{quantity}份合格材料，实有{len(types[kind])}份、合格{len(qualified)}份", "；".join(m.path.name for m in types[kind]))
        elif condition:
            already_selected = [m for m in qualified if m.selected_as_basis]
            if not already_selected:
                for material in sorted(qualified, key=lambda m: m.ocr_confidence or 0, reverse=True)[:quantity]:
                    material.selected_as_basis = True
            _add(result, "材料完整性", kind, "齐全", reason + "；同类多份时至少一份合格即判定齐全", f"实有{len(types[kind])}份、合格{len(qualified)}份", "；".join(m.path.name for m in qualified))
        else:
            _add(result, "材料完整性", kind, "不适用", f"当前人员情况未触发：{reason}", f"实有{len(types[kind])}份", "；".join(m.path.name for m in types[kind]))

    require("申报表", True, "《福建省职业技能等级认定申报表》为必交材料")
    if types["申报表"] and not any("福建省职业技能等级认定申报表" in "".join(m.text_pages).replace(" ", "") for m in types["申报表"]):
        _add(result, "材料完整性", "申报表全称", "人工复核", "已发现申报表文件，但未可靠识别到全称《福建省职业技能等级认定申报表》，请人工确认", sources="；".join(m.path.name for m in types["申报表"]))
    require("证件照", True, "证件照为必交材料")
    require("身份证", True, "身份证为必交材料")
    is_higher_student = preset.is_college_student or (
        level in HIGHER_EDUCATION and student_status in IN_SCHOOL
    )
    require(
        "学历证明",
        not is_higher_student,
        "大专及以上在籍/在校人员以学信网学籍材料为依据，无需提交毕业证；已毕业人员须提交最高学历毕业证",
    )
    chsi_materials = [m for kind in CHSI_TYPES for m in types[kind] if _usable_material(m)]
    chsi_count = len(chsi_materials)
    force_chsi = "学信网材料" in forced
    chsi_required = level in HIGHER_EDUCATION or preset.is_college_student or force_chsi
    if chsi_required and not chsi_count:
        reason = "操作面板已勾选为本批次强制材料" if force_chsi else "大专及以上人员无论在校或毕业均须提交学信网材料"
        _add(result, "材料完整性", "学信网材料", "缺少材料", reason, "应有至少1份，实有0份")
    elif chsi_required:
        for material in chsi_materials:
            material.selected_as_basis = True
        reason = "操作面板已勾选为强制材料；已提交学信网材料" if force_chsi else "已提交学信网材料"
        _add(result, "材料完整性", "学信网材料", "齐全", reason, f"共{chsi_count}份")
    else:
        _add(result, "材料完整性", "学信网材料", "不适用", "当前识别学历未达到大专及以上，未触发学信网材料要求", f"实有{chsi_count}份")
    graduated = preset.is_graduated or (bool(level) and student_status not in IN_SCHOOL)
    if graduated and not form_work:
        _add(result, "申报表填写核验", "工作经历", "缺少信息", "只有未毕业的在籍/在校人员允许工作经历为空；已毕业人员至少填写一段完整工作经历")
    usable_proofs = [m for m in types["工作证明"] if _usable_material(m)]
    usable_screenshots = [m for m in types["企业信息截图"] if _usable_material(m)]
    manual_work = preset.is_working or preset.work_history in {"1份", "2份及以上"}
    manual_no_work = preset.work_history == "无"
    inferred_has_work = False if manual_no_work else bool(form_work or graduated or manual_work or usable_proofs or usable_screenshots)
    if inferred_has_work:
        for group in (usable_proofs, usable_screenshots):
            for material in group:
                material.selected_as_basis = True
    require("工作证明", inferred_has_work, "有工作经历时，仅最后一段工作经历必须有工作证明")
    multiple_work = len(form_work) > 1 or preset.work_history == "2份及以上"
    require("工作年限承诺书", multiple_work, "有2段及以上工作经历必须提交工作年限承诺书")
    # 每个不同企业均须有一份截图；同企业多段经历只要求一份。
    companies = {normalize_company(w.company) for w in form_work if w.company}
    require("企业信息截图", inferred_has_work, "每个工作经历企业均须提交企业信息截图", max(1, len(companies)))
    require("职业技能等级认定承诺书", False, "仅在操作面板勾选时强制提交")
    require("其他材料", False, "仅在操作面板勾选时强制至少提交一份其他材料")


def _compare_form_to_id(result: PersonResult, form: Material | None, identity: Material | None) -> None:
    if not form or not identity:
        return
    f = _by_field(form.evidences)
    i = _by_field(identity.evidences)
    expected = {
        "姓名": i.get("姓名", [None])[0].normalized_value if i.get("姓名") else "",
        "性别": i.get("性别", [None])[0].normalized_value if i.get("性别") else "",
        "身份证号": i.get("身份证号", [None])[0].normalized_value if i.get("身份证号") else "",
        "出生日期": i.get("出生日期", [None])[0].normalized_value if i.get("出生日期") else "",
    }
    if expected["身份证号"]:
        expected["出生日期"] = birthday_from_id(expected["身份证号"])
        expected["性别"] = gender_from_id(expected["身份证号"])
    for field, authoritative in expected.items():
        form_values = f.get(field, [])
        if not form_values:
            _add(result, "身份信息核对", field, "缺少信息", f"申报表未可靠读取到{field}", sources=form.path.name)
            continue
        submitted = form_values[0].normalized_value
        if field in {"出生日期"}:
            submitted, authoritative = format_year_month(submitted), format_year_month(authoritative)
        status = "一致" if authoritative and submitted == authoritative else "不一致"
        _add(result, "身份信息核对", field, status, f"申报表{field}与身份证{'一致' if status == '一致' else '不一致'}", f"申报表={submitted}；身份证={authoritative}", f"{form.path.name}；{identity.path.name}")


def _education_rules(result: PersonResult, materials: list[Material], form: Material | None) -> tuple[str, str, str]:
    higher = [m for m in materials if m.document_type in CHSI_TYPES and _usable_material(m)]
    diplomas = [m for m in materials if m.document_type == "学历证明" and _usable_material(m)]
    candidates = higher + diplomas

    def education_score(material: Material) -> tuple[int, int, int, float]:
        fields = _by_field(material.evidences)
        level = fields.get("学历层次", [None])[0].normalized_value if fields.get("学历层次") else ""
        authoritative = 2 if material.document_type in CHSI_TYPES else 1
        completeness = sum(bool(fields.get(field)) for field in ("毕业院校", "毕业时间", "毕业证编码", "学籍状态"))
        confidence = material.ocr_confidence if material.ocr_confidence is not None else 1.0
        return (LEVEL_RANK.get(level, 0), authoritative, completeness, confidence)

    authority = max(candidates, key=education_score) if candidates else None
    if authority: authority.selected_as_basis = True
    fields = _by_field(authority.evidences) if authority else {}
    level = fields.get("学历层次", [None])[0].normalized_value if fields.get("学历层次") else ""
    status = fields.get("学籍状态", [None])[0].normalized_value if fields.get("学籍状态") else ""
    # 学籍状态为“在籍/在校”时尚未毕业，核验申报表毕业时间应采用预计毕业日期。
    # 已毕业人员仍采用毕业时间，且材料完整性规则继续要求最高学历毕业证。
    if status in IN_SCHOOL and fields.get("预计毕业时间"):
        grad = fields["预计毕业时间"][0].normalized_value
    else:
        grad = fields.get("毕业时间", [None])[0].normalized_value if fields.get("毕业时间") else ""
    same_rank = [
        material for material in candidates
        if material is not authority and education_score(material)[0] == education_score(authority)[0]
    ] if authority else []
    for field in ("毕业院校", "毕业时间", "毕业证编码"):
        selected_value = fields.get(field, [None])[0].normalized_value if fields.get(field) else ""
        conflicts = {
            e.normalized_value for material in same_rank
            for e in _material_evidence(material, field)
            if e.normalized_value and selected_value and e.normalized_value != selected_value
        }
        if conflicts:
            _add(result, "学历信息", field, "人工复核", "同层次学历材料之间存在信息冲突，不能静默择优", f"采用={selected_value}；其他={'、'.join(sorted(conflicts))}", authority.path.name)
    # 不能从申报表空白栏目标题（如“高职/本科”）推断实际学历层次。
    if form and authority:
        form_fields = _by_field(form.evidences)
        form_level = form_fields.get("学历层次", [None])[0].normalized_value if form_fields.get("学历层次") else ""
        if not form_level or not level:
            _add(
                result, "学习经历核对", "最高学历", "无法核对",
                "未能同时可靠读取申报表最高学历和学历核验依据，请人工复核",
                f"申报表={form_level}；依据={level}", f"{form.path.name}；{authority.path.name}",
            )
        else:
            same_level = LEVEL_RANK.get(form_level, 0) == LEVEL_RANK.get(level, 0)
            _add(
                result, "学习经历核对", "最高学历", "一致" if same_level else "不一致",
                "申报表最高学历与学历核验依据比较",
                f"申报表={form_level}；依据={level}", f"{form.path.name}；{authority.path.name}",
            )
        for field in ("毕业院校", "毕业时间"):
            expected = grad if field == "毕业时间" else fields.get(field, [None])[0].normalized_value if fields.get(field) else ""
            actual = form_fields.get(field, [None])[0].normalized_value if form_fields.get(field) else ""
            if field == "毕业时间": expected, actual = format_year_month(expected), format_year_month(actual)
            if not actual or not expected:
                _add(result, "学习经历核对", field, "无法核对", "现有材料无法完整核实该项学习经历，请人工复核或补充证明材料", f"申报表={actual}；依据={expected}")
            else:
                _add(result, "学习经历核对", field, "一致" if actual == expected else "不一致", f"申报表{field}与核验依据比较", f"申报表={actual}；依据={expected}", f"{form.path.name}；{authority.path.name}")
        if status:
            _add(
                result,
                "学习经历核对",
                "学籍状态",
                "在籍" if status in IN_SCHOOL else status,
                "学信网学籍状态显示在籍/在校时，表示尚未毕业，并以预计毕业日期核验申报表",
                status,
                authority.path.name,
            )
        if not any("初中" in p for p in form.text_pages):
            _add(result, "学习经历核对", "初中经历", "缺少信息", "申报表学习经历必须从初中开始填写", sources=form.path.name)
        else:
            _add(result, "学习经历核对", "初中经历", "已填写", "申报表学习经历已包含初中阶段；如无证明材料，仍需人工复核校名与时间", sources=form.path.name)
    if authority and authority.document_type == "学历证明" and level and level != "初中" and not fields.get("毕业证编码"):
        _add(result, "学历信息", "毕业证编码", "缺少信息", "除初中学历外，最高学历证明存在编码时应填写；未可靠识别到毕业证编码", sources=authority.path.name)
    return level, status, grad


def _commitment_rules(result: PersonResult, materials: list[Material], all_work: list[WorkRecord], identity: Material | None, form_work: list[WorkRecord]) -> None:
    commitments = [m for m in materials if m.document_type == "工作年限承诺书" and _usable_material(m)]
    if not commitments:
        return
    records = [w for w in all_work if w.source_type == "工作年限承诺书"]
    fields = _by_field([e for m in commitments for e in m.evidences])
    identity_fields = _by_field(identity.evidences) if identity else {}
    for field in ("姓名", "身份证号"):
        expected = identity_fields.get(field, [None])[0].normalized_value if identity_fields.get(field) else ""
        actual = fields.get(field, [None])[0].normalized_value if fields.get(field) else ""
        if not actual:
            _add(result, "承诺函核对", field, "缺少信息", f"工作年限承诺书未可靠读取到{field}", sources="；".join(m.path.name for m in commitments))
        elif expected:
            _add(result, "承诺函核对", field, "一致" if actual == expected else "不一致", f"工作年限承诺书{field}与身份证核对", f"承诺书={actual}；身份证={expected}", "；".join(m.path.name for m in commitments))
    if not fields.get("承诺人签名"):
        _add(result, "承诺函核对", "本人签名", "缺少信息", "工作年限承诺书未可靠识别到考生本人签名")
    stated = int(fields["承诺工作年限"][0].normalized_value) if fields.get("承诺工作年限") else None
    calculated = sum(duration_months(w.start, w.end) or 0 for w in records)
    if stated is not None and records:
        status = "一致" if stated == calculated else "人工复核"
        _add(result, "承诺函核对", "工作年限", status, "承诺的总工作年限与逐段月份合计核对", f"声明={stated}个月；逐段合计={calculated}个月")
    if form_work and not records:
        _add(result, "承诺函核对", "完整工作经历", "缺少信息", "工作年限承诺书必须填写申报表中的全部工作经历，当前未可靠读取到逐段经历", sources="；".join(m.path.name for m in commitments))
    elif form_work:
        form_ordered = sorted(form_work, key=lambda w: month_index(w.start) or 0)
        commitment_ordered = sorted(records, key=lambda w: month_index(w.start) or 0)
        _add(result, "承诺函核对", "工作经历段数", "一致" if len(form_ordered) == len(commitment_ordered) else "不一致", "工作年限承诺书必须完整填写申报表中的全部工作经历，不得只填写最后一段", f"申报表={len(form_ordered)}段；承诺书={len(commitment_ordered)}段")
        for index, (form_record, commitment_record) in enumerate(zip(form_ordered, commitment_ordered), 1):
            comparisons = (
                ("开始时间", form_record.start, commitment_record.start),
                ("结束时间", form_record.end, commitment_record.end),
                ("企业名称", form_record.company, commitment_record.company),
                ("从事职业", form_record.occupation, commitment_record.occupation),
            )
            for field, expected, actual in comparisons:
                status = "一致" if expected and actual and expected == actual else "不一致"
                _add(result, "承诺函核对", f"第{index}段{field}", status, "承诺书逐段工作经历与申报表核对", f"申报表={expected}；承诺书={actual}", commitment_record.source)
        form_total = sum(duration_months(w.start, w.end) or 0 for w in form_ordered)
        commitment_total = sum(duration_months(w.start, w.end) or 0 for w in commitment_ordered)
        _add(result, "承诺函核对", "全部工作月份", "一致" if form_total == commitment_total else "不一致", "承诺书全部工作月份与申报表全部工作月份合计核对", f"申报表={form_total}个月；承诺书={commitment_total}个月")
    ordered = sorted(records, key=lambda w: month_index(w.start) or 0)
    for previous, current in zip(ordered, ordered[1:]):
        if (month_index(current.start) or 0) <= (month_index(previous.end) or -1):
            _add(result, "承诺函核对", "工作经历重叠", "不一致", "承诺函内工作经历不能重叠；允许断档", f"{previous.company}；{current.company}")


def _work_rules(result: PersonResult, materials: list[Material], records: list[WorkRecord], all_records: list[WorkRecord], graduation: str, identity: Material | None, registry: CompanyRegistry, cfg: AppConfig) -> None:
    for record in records:
        record.duration_months = duration_months(record.start, record.end)
        company_status, company_message = registry.validate(record.company)
        record.company_status, record.company_message = company_status, company_message
        if company_status != "通过":
            _add(result, "企业名称", "企业全称", company_status, company_message, record.company, record.source)
        if record.end != "至今" and record.duration_months is None:
            _add(result, "时间逻辑", "工作起止时间", "不一致", "工作结束时间早于开始时间或日期无法识别", f"{format_year_month(record.start)}-{format_year_month(record.end)}", record.source)
        if record.source_type == "申报表" and (not record.witness_name or not record.witness_phone):
            _add(result, "工作经历核对", "证明人姓名、电话", "缺少信息", "申报表每段工作经历必须填写证明人姓名和电话", f"企业={record.company}；证明人={record.witness_name}；电话={record.witness_phone}", record.source)

    ordered = sorted([r for r in records if month_index(r.start) is not None], key=lambda r: month_index(r.start) or 0)
    if ordered:
        total_months = sum(record.duration_months or 0 for record in ordered)
        years, months = divmod(total_months, 12)
        _add(result, "工作经历核对", "累计工作年限", "已计算", "按申报表各段工作经历逐月累计；工作经历不得重叠，允许断档，至今按当前月份计算", f"{years}年{months}个月（共{total_months}个月）", "；".join(record.source for record in ordered))
        forms = [m for m in materials if m.document_type == "申报表" and _usable_material(m)]
        stated_values = _by_field(forms[0].evidences).get("从事本职业年限", []) if forms else []
        if stated_values:
            stated_months = int(stated_values[0].normalized_value)
            status = "一致" if stated_months == total_months else "人工复核"
            _add(result, "工作经历核对", "从事本职业年限", status, "申报表填写的从事本职业年限与各段工作月份合计核对", f"申报表={stated_months // 12}年；逐段合计={years}年{months}个月", forms[0].path.name)
        else:
            _add(result, "工作经历核对", "从事本职业年限", "缺少信息", "申报表有工作经历时必须填写从事本职业年限")
    if ordered:
        latest = ordered[-1]
        proofs = [m for m in materials if m.document_type == "工作证明" and _usable_material(m)]
        for proof in proofs:
            proof.selected_as_basis = True
        proof_records = [record for record in all_records if record.source_type == "工作证明"]
        proof_companies = {
            e.normalized_value for m in proofs for e in m.evidences
            if e.field in {"企业名称", "出具单位"}
        } | {record.company for record in proof_records if record.company}
        if not proofs:
            pass  # 材料完整性规则已报告缺失。
        elif proof_companies and latest.company not in proof_companies:
            _add(result, "工作证明核对", "最后一份工作", "不一致", "工作证明中的企业名称与最后一段工作经历企业全称不一致", f"最后工作={latest.company}；证明企业={'、'.join(sorted(proof_companies))}", latest.source)
        elif not proof_companies:
            _add(result, "工作证明核对", "最后一份工作", "人工复核", "已提交工作证明，但未可靠读取到企业全称，需人工确认其对应最后一段工作经历", latest.company, latest.source)
        else:
            _add(result, "工作证明核对", "最后一份工作", "一致", "最后一段工作经历已有对应工作证明", latest.company, latest.source)
        for proof in proofs:
            proof_fields = _by_field(proof.evidences)
            if not proof_fields.get("证明人姓名") or not proof_fields.get("证明人电话"):
                _add(result, "工作证明核对", "证明人及电话", "缺少信息", "工作证明必须填写证明人姓名和联系电话", sources=proof.path.name)
            sealed = bool(proof_fields.get("公章状态"))
            if cfg.audit_mode == "正式审核" and not sealed:
                _add(result, "工作证明核对", "单位公章", "缺少材料", "正式审核的工作证明必须加盖单位公章", sources=proof.path.name)
            elif cfg.audit_mode == "预审" and not sealed:
                _add(result, "工作证明核对", "单位公章", "人工复核", "预审阶段允许暂未盖章；正式提交时必须加盖单位公章", sources=proof.path.name)
            elif sealed:
                _add(result, "工作证明核对", "单位公章", "已检测", "检测到红色公章；圆形公章文字低置信度时仍需人工复核", sources=proof.path.name)
            if identity:
                identity_fields = _by_field(identity.evidences)
                for field in ("姓名", "身份证号"):
                    expected = identity_fields.get(field, [None])[0].normalized_value if identity_fields.get(field) else ""
                    actual = proof_fields.get(field, [None])[0].normalized_value if proof_fields.get(field) else ""
                    if not actual:
                        _add(result, "工作证明核对", field, "缺少信息", f"工作证明未可靠读取到{field}", sources=proof.path.name)
                    elif expected and actual != expected:
                        _add(result, "工作证明核对", field, "不一致", f"工作证明{field}与身份证不一致", f"工作证明={actual}；身份证={expected}", proof.path.name)
            stated_proof = proof_fields.get("证明工作年限", [])
            if not stated_proof:
                _add(result, "工作证明核对", "工作年限", "缺少信息", "工作证明须按“自×年×月至今，在××企业从事××职位×年”填写工作年限", sources=proof.path.name)
        matching_proofs = [record for record in proof_records if record.company == latest.company]
        if proofs and not matching_proofs:
            _add(result, "工作证明核对", "规范工作陈述", "缺少信息", "未从工作证明可靠读取到“自×年×月至今，在××企业从事××职位×年”的完整陈述", sources="；".join(m.path.name for m in proofs))
        for proof_record in matching_proofs:
            if proof_record.start and latest.start and proof_record.start != latest.start:
                _add(result, "工作证明核对", "工作开始时间", "不一致", "工作证明开始时间与最后一段工作经历不一致", f"申报表={format_year_month(latest.start)}；工作证明={format_year_month(proof_record.start)}", proof_record.source)
            if proof_record.end and latest.end and proof_record.end != latest.end:
                _add(result, "工作证明核对", "工作结束时间", "不一致", "工作证明结束时间与最后一段工作经历不一致", f"申报表={format_year_month(latest.end)}；工作证明={format_year_month(proof_record.end)}", proof_record.source)
            if proof_record.occupation and latest.occupation and proof_record.occupation != latest.occupation:
                _add(result, "工作证明核对", "从事职业", "人工复核", "工作证明岗位与申报表最后一段岗位文字不完全一致，请确认是否为同一职业", f"申报表={latest.occupation}；工作证明={proof_record.occupation}", proof_record.source)
            proof_material = next((m for m in proofs if m.path.name in proof_record.source), None)
            proof_fields = _by_field(proof_material.evidences) if proof_material else {}
            stated = proof_fields.get("证明工作年限", [])
            calculated = duration_months(proof_record.start, proof_record.end)
            if stated and calculated is not None:
                stated_months = int(stated[0].normalized_value)
                # “工作×年”按完整周年填写，月份不足一年部分允许省略。
                status = "一致" if stated_months // 12 == calculated // 12 else "不一致"
                _add(result, "工作证明核对", "工作年限", status, "工作证明填写年限与证明中的起止月份核对", f"填写={stated_months // 12}年；计算={calculated // 12}年{calculated % 12}个月", proof_record.source)
    for previous, current in zip(ordered, ordered[1:]):
        previous_end = month_index(previous.end) if previous.end != "至今" else 999999
        current_start = month_index(current.start)
        if previous_end is not None and current_start is not None and current_start <= previous_end:
            _add(result, "时间逻辑", "工作经历重叠", "不一致", "工作经历不能重叠；允许断档", f"{previous.company} {format_year_month(previous.start)}-{format_year_month(previous.end)}；{current.company} {format_year_month(current.start)}-{format_year_month(current.end)}")

    if ordered and graduation:
        first_start, graduation_month = month_index(ordered[0].start), month_index(graduation)
        if first_start is not None and graduation_month is not None and first_start <= graduation_month:
            _add(result, "时间逻辑", "毕业后参加工作", "不一致", "第一份工作必须从毕业次月或之后开始", f"毕业={format_year_month(graduation)}；工作开始={format_year_month(ordered[0].start)}")
    if ordered and identity:
        ids = _material_evidence(identity, "身份证号")
        birth_month = month_index(birthday_from_id(ids[0].normalized_value)) if ids else None
        first_start = month_index(ordered[0].start)
        if birth_month is not None and first_start is not None and first_start < birth_month + 16 * 12:
            _add(result, "时间逻辑", "首次工作年龄", "不一致", "第一份工作开始时必须年满16周岁", f"出生={format_year_month(birthday_from_id(ids[0].normalized_value))}；工作开始={format_year_month(ordered[0].start)}")

    company_scopes: dict[str, list[str]] = defaultdict(list)
    for material in materials:
        if material.document_type != "企业信息截图" or not _usable_material(material):
            continue
        fields = _by_field(material.evidences)
        companies = [e.normalized_value for e in fields.get("企业名称", [])]
        scopes = [e.normalized_value for e in fields.get("经营范围", [])]
        for company in companies:
            company_scopes[company].extend(scopes)
    screenshot_companies = set(company_scopes)
    for record in records:
        if record.company not in screenshot_companies:
            _add(result, "企业信息核对", "企业信息截图", "缺少或不一致", "未找到与该段工作经历企业全称完全一致的企业信息截图", record.company, record.source)
        else:
            record.company_status = "通过"
            record.company_message = "与企业信息截图中的工商登记名称完全一致"
            for material in materials:
                if material.document_type == "企业信息截图" and any(
                    e.field == "企业名称" and e.normalized_value == record.company
                    for e in material.evidences
                ):
                    material.selected_as_basis = True
        occupation = record.occupation
        if occupation and any(word in occupation for word in cfg.functional_positions):
            _add(result, "经营范围核对", "从事职业", "豁免", "职能类岗位不受企业经营范围限制", occupation, record.source)
        elif occupation:
            keywords = next((v for k, v in cfg.occupation_scope_keywords.items() if k in occupation), (occupation,))
            corresponding_scopes = company_scopes.get(record.company, [])
            matched = any(any(keyword in scope for keyword in keywords) for scope in corresponding_scopes)
            _add(result, "经营范围核对", "从事职业", "一致" if matched else "人工复核", "从事职业需属于对应企业经营范围" if matched else "未能从企业信息截图经营范围中确认该职业，请人工复核", occupation, record.source)


def evaluate(person: str, materials: list[Material], evidences: list[Evidence], work: list[WorkRecord], registry: CompanyRegistry, cfg: AppConfig | None = None) -> PersonResult:
    cfg = cfg or AppConfig()
    result = PersonResult(person=person, materials=materials)
    usable_types = {
        material.document_type for material in materials if _usable_material(material)
    }
    good_photos = [m for m in materials if m.document_type == "证件照" and _usable_material(m)]
    for material in materials:
        for error in material.errors:
            status = "材料不采用" if material.document_type in usable_types else "待复核"
            _add(result, "处理异常", "文件读取", status, error, sources=material.path.name)
        if material.document_type == "证件照":
            if _usable_material(material):
                _add(result, "材料质量", "证件照", "通过", "证件照为二寸比例的半身彩色照片；无需提取文字", sources=material.path.name)
            else:
                status = "材料不采用" if good_photos else "退回"
                _add(result, "材料质量", "证件照", status, "证件照不符合要求：" + "；".join(material.quality_reasons), sources=material.path.name)
        for evidence in material.evidences:
            if evidence.field in KEY_OCR_FIELDS and evidence.confidence is not None and evidence.confidence < 0.65:
                _add(result, "识别置信度", evidence.field, "人工复核", "关键字段OCR置信度较低，不自动据此判定不一致", f"{evidence.normalized_value}（置信度{evidence.confidence:.0%}）", f"{evidence.file} 第{evidence.page}页")

    identity = _select_valid_id(materials, result)
    forms = [m for m in materials if m.document_type == "申报表"]
    usable_forms = [m for m in forms if _usable_material(m)]
    form = max(usable_forms, key=lambda m: (m.ocr_confidence or 0, len(m.evidences))) if usable_forms else (forms[0] if forms else None)
    if form: form.selected_as_basis = True
    form_work = [w for w in work if w.source_type == "申报表"]
    proof_work = [w for w in work if w.source_type == "工作证明"]
    if form and not form_work:
        form_text = "\n".join(form.text_pages)
        if re.search(r"(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月.{0,40}(?:至|到)", form_text, re.S):
            _add(result, "工作经历核对", "工作经历解析", "待复核", "申报表疑似填写了工作经历，但未能转换为结构化记录，请人工复核", sources=form.path.name)
    result.work_records = form_work if form_work else proof_work
    if form and not form_work and (proof_work or any(m.document_type == "企业信息截图" for m in materials)):
        _add(result, "工作经历核对", "申报表工作经历", "缺少信息", "已提交工作证明或企业信息截图，但未从申报表读取到完整工作经历；不能仅用辅助材料替代申报表记录", sources=form.path.name)
    level, student_status, graduation = _education_rules(result, materials, form)
    level, student_status, graduation = _apply_review_preset(
        result, level, student_status, graduation, form_work, cfg
    )
    if not level:
        _add(result, "学历信息", "学历层次", "人工复核", "未能从现有材料可靠判断学历层次，学信网材料要求需人工复核")
    _required_materials(result, materials, form_work, level, student_status, cfg)
    _compare_form_to_id(result, form, identity)
    _work_rules(result, materials, form_work, work, graduation, identity, registry, cfg)
    _commitment_rules(result, materials, work, identity, form_work)

    statuses = [f.status for f in result.findings]
    overall = "通过"
    if any(x in {"退回", "不一致", "缺少材料", "缺少或不一致"} for x in statuses): overall = "不通过"
    elif any(x in {"待复核", "人工复核", "无法核对", "缺少信息"} for x in statuses): overall = "待复核"
    result.summary = {
        "总体结果": overall,
        "材料数": len(materials),
        "退回数": sum(f.status == "退回" for f in result.findings),
        "不一致数": sum(f.status in {"不一致", "缺少或不一致"} for f in result.findings),
        "待复核数": sum(f.status in {"待复核", "人工复核", "无法核对", "缺少信息"} for f in result.findings),
    }
    return result
