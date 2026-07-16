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


def _required_materials(result: PersonResult, materials: list[Material], form_work: list[WorkRecord], level: str, student_status: str) -> None:
    types = defaultdict(list)
    for material in materials:
        types[material.document_type].append(material)

    def require(kind: str, condition: bool, reason: str, quantity: int = 1) -> None:
        if condition and len(types[kind]) < quantity:
            _add(result, "材料完整性", kind, "缺少材料", f"缺少{kind}。触发条件：{reason}", f"应有{quantity}份，实有{len(types[kind])}份")
        elif condition:
            _add(result, "材料完整性", kind, "齐全", reason, f"共{len(types[kind])}份")

    require("申报表", True, "《福建省职业技能等级认定申报表》为必交材料")
    if types["申报表"] and not any("福建省职业技能等级认定申报表" in "".join(m.text_pages).replace(" ", "") for m in types["申报表"]):
        _add(result, "材料完整性", "申报表全称", "人工复核", "已发现申报表文件，但未可靠识别到全称《福建省职业技能等级认定申报表》，请人工确认", sources="；".join(m.path.name for m in types["申报表"]))
    require("证件照", True, "证件照为必交材料")
    require("身份证", True, "身份证为必交材料")
    is_higher_student = level in {"高职", "本科"} and student_status in IN_SCHOOL
    require("学历证明", not is_higher_student, "非高职、本科在校生必须提交最高学历证明")
    chsi_count = sum(len(types[kind]) for kind in CHSI_TYPES)
    if level in HIGHER_EDUCATION and not chsi_count:
        _add(result, "材料完整性", "学信网材料", "缺少材料", "大专及以上人员无论在校或毕业均须提交学信网材料", "应有至少1份，实有0份")
    elif level in HIGHER_EDUCATION:
        _add(result, "材料完整性", "学信网材料", "齐全", "已提交学信网材料", f"共{chsi_count}份")
    require("工作证明", bool(form_work), "有工作经历时，仅最后一段工作经历必须有工作证明")
    require("工作年限承诺书", len(form_work) > 1, "有2段及以上工作经历必须提交工作年限承诺书")
    # 每个不同企业均须有一份截图；同企业多段经历只要求一份。
    companies = {normalize_company(w.company) for w in form_work if w.company}
    require("企业信息截图", bool(companies), "每个工作经历企业均须提交企业信息截图", len(companies))


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
    higher = [m for m in materials if m.document_type in CHSI_TYPES]
    diplomas = [m for m in materials if m.document_type == "学历证明"]
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
        for field in ("毕业院校", "毕业时间"):
            expected = fields.get(field, [None])[0].normalized_value if fields.get(field) else ""
            actual = form_fields.get(field, [None])[0].normalized_value if form_fields.get(field) else ""
            if field == "毕业时间": expected, actual = format_year_month(expected), format_year_month(actual)
            if not actual or not expected:
                _add(result, "学习经历核对", field, "无法核对", "现有材料无法完整核实该项学习经历，请人工复核或补充证明材料", f"申报表={actual}；依据={expected}")
            else:
                _add(result, "学习经历核对", field, "一致" if actual == expected else "不一致", f"申报表{field}与核验依据比较", f"申报表={actual}；依据={expected}", f"{form.path.name}；{authority.path.name}")
        if not any("初中" in p for p in form.text_pages):
            _add(result, "学习经历核对", "初中经历", "缺少信息", "申报表学习经历必须从初中开始填写", sources=form.path.name)
        else:
            _add(result, "学习经历核对", "初中经历", "已填写", "申报表学习经历已包含初中阶段；如无证明材料，仍需人工复核校名与时间", sources=form.path.name)
    if authority and authority.document_type == "学历证明" and level and level != "初中" and not fields.get("毕业证编码"):
        _add(result, "学历信息", "毕业证编码", "缺少信息", "除初中学历外，最高学历证明存在编码时应填写；未可靠识别到毕业证编码", sources=authority.path.name)
    return level, status, grad


def _commitment_rules(result: PersonResult, materials: list[Material], all_work: list[WorkRecord]) -> None:
    commitments = [m for m in materials if m.document_type == "工作年限承诺书"]
    if not commitments:
        return
    records = [w for w in all_work if w.source_type == "工作年限承诺书"]
    fields = _by_field([e for m in commitments for e in m.evidences])
    if not fields.get("承诺人签名"):
        _add(result, "承诺函核对", "本人签名", "缺少信息", "工作年限承诺书未可靠识别到考生本人签名")
    stated = int(fields["承诺工作年限"][0].normalized_value) if fields.get("承诺工作年限") else None
    calculated = sum(duration_months(w.start, w.end) or 0 for w in records)
    if stated is not None and records:
        status = "一致" if stated == calculated else "人工复核"
        _add(result, "承诺函核对", "工作年限", status, "承诺的总工作年限与逐段月份合计核对", f"声明={stated}个月；逐段合计={calculated}个月")
    ordered = sorted(records, key=lambda w: month_index(w.start) or 0)
    for previous, current in zip(ordered, ordered[1:]):
        if (month_index(current.start) or 0) <= (month_index(previous.end) or -1):
            _add(result, "承诺函核对", "工作经历重叠", "不一致", "承诺函内工作经历不能重叠；允许断档", f"{previous.company}；{current.company}")


def _work_rules(result: PersonResult, materials: list[Material], records: list[WorkRecord], all_records: list[WorkRecord], graduation: str, identity: Material | None, registry: CompanyRegistry, cfg: AppConfig) -> None:
    for record in records:
        record.duration_months = None if record.end == "至今" else duration_months(record.start, record.end)
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
        latest = ordered[-1]
        proofs = [m for m in materials if m.document_type == "工作证明"]
        proof_companies = {
            e.normalized_value for m in proofs for e in m.evidences
            if e.field in {"企业名称", "出具单位"}
        }
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
        proof_records = [record for record in all_records if record.source_type == "工作证明"]
        matching_proofs = [record for record in proof_records if record.company == latest.company]
        for proof_record in matching_proofs:
            if proof_record.start and latest.start and proof_record.start != latest.start:
                _add(result, "工作证明核对", "工作开始时间", "不一致", "工作证明开始时间与最后一段工作经历不一致", f"申报表={format_year_month(latest.start)}；工作证明={format_year_month(proof_record.start)}", proof_record.source)
            if proof_record.end and latest.end and proof_record.end != latest.end:
                _add(result, "工作证明核对", "工作结束时间", "不一致", "工作证明结束时间与最后一段工作经历不一致", f"申报表={format_year_month(latest.end)}；工作证明={format_year_month(proof_record.end)}", proof_record.source)
            if proof_record.occupation and latest.occupation and proof_record.occupation != latest.occupation:
                _add(result, "工作证明核对", "从事职业", "人工复核", "工作证明岗位与申报表最后一段岗位文字不完全一致，请确认是否为同一职业", f"申报表={latest.occupation}；工作证明={proof_record.occupation}", proof_record.source)
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
        if material.document_type != "企业信息截图":
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
    for material in materials:
        for error in material.errors:
            _add(result, "处理异常", "文件读取", "待复核", error, sources=material.path.name)
        if material.document_type == "证件照":
            if material.quality_status == "合格":
                _add(result, "材料质量", "证件照", "通过", "证件照为二寸比例的半身彩色照片；无需提取文字", sources=material.path.name)
            else:
                _add(result, "材料质量", "证件照", "退回", "证件照不符合要求：" + "；".join(material.quality_reasons), sources=material.path.name)
        for evidence in material.evidences:
            if evidence.field in KEY_OCR_FIELDS and evidence.confidence is not None and evidence.confidence < 0.65:
                _add(result, "识别置信度", evidence.field, "人工复核", "关键字段OCR置信度较低，不自动据此判定不一致", f"{evidence.normalized_value}（置信度{evidence.confidence:.0%}）", f"{evidence.file} 第{evidence.page}页")

    identity = _select_valid_id(materials, result)
    forms = [m for m in materials if m.document_type == "申报表"]
    form = forms[0] if forms else None
    if form: form.selected_as_basis = True
    form_work = [w for w in work if w.source_type == "申报表"]
    if form and not form_work:
        form_text = "\n".join(form.text_pages)
        if re.search(r"(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月.{0,40}(?:至|到)", form_text, re.S):
            _add(result, "工作经历核对", "工作经历解析", "待复核", "申报表疑似填写了工作经历，但未能转换为结构化记录，请人工复核", sources=form.path.name)
    if not form_work:
        form_work = [w for w in work if w.source_type not in {"企业信息截图", "工作证明"}]
    result.work_records = form_work
    level, student_status, graduation = _education_rules(result, materials, form)
    if not level:
        _add(result, "学历信息", "学历层次", "人工复核", "未能从现有材料可靠判断学历层次，学信网材料要求需人工复核")
    _required_materials(result, materials, form_work, level, student_status)
    _compare_form_to_id(result, form, identity)
    _work_rules(result, materials, form_work, work, graduation, identity, registry, cfg)
    _commitment_rules(result, materials, work)

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
