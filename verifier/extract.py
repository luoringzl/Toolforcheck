from __future__ import annotations

import re

from .idcard import validate_cn_id
from .models import Evidence, Material, WorkRecord
from .normalize import normalize_company, normalize_date, normalize_id, normalize_name

ARABIC_DATE = r"(?:19\d{2}|20\d{2})[年./\-]\d{1,2}(?:(?:月(?:\d{1,2}日?)?)|(?:[./\-]\d{1,2}日?))?"
CHINESE_DATE = r"[〇○O零一二三四五六七八九]{4}年[一二三四五六七八九十]{1,3}月(?:[一二三四五六七八九十]{1,3}日)?"
DATE = rf"(?:{ARABIC_DATE}|{CHINESE_DATE})"


def _first(patterns: list[str], text: str, flags: int = 0) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip(" ：:\t，,。")
    return ""


def _labelled_date(text: str, labels: tuple[str, ...], max_gap: int = 100) -> str:
    """读取表格标签后的首个日期，容忍PDF把同一行单元格打散或夹入其他标签。"""
    text = re.sub(r"[\s　]+", "", text)
    label = "|".join(re.escape(value) for value in labels)
    # 申报表PDF文本层不一定按视觉上的行顺序输出；允许标签与值之间出现少量
    # 非日期文字，但遇到第一个阿拉伯年份后即必须由DATE完整匹配。
    pattern = rf"(?:{label})\s*[：:]?(?:(?!(?:19|20)\d{{2}}).){{0,{max_gap}}}?({DATE})"
    return _first([pattern], text, re.S)


def _best_id(text: str) -> str:
    labelled = re.findall(r"(?:公民身份号码|身份证(?:号码|号)?)\s*[：:]?\s*([0-9Xx\s]{18,28})", text)
    compact = re.sub(r"\s", "", text)
    general = re.findall(r"(?<!\d)([1-9]\d{16}[0-9Xx])(?!\d)", compact)
    # Word文本框和OCR有时会在身份证号码中插入点、下划线或短横线。
    separated = re.findall(r"(?<![0-9Xx])([1-9][0-9Xx·._\-\s]{17,38})(?![0-9Xx])", text)
    candidates = []
    for raw in labelled + general + separated:
        number = normalize_id(raw)
        if len(number) == 18 and number not in candidates:
            candidates.append(number)
    valid = [number for number in candidates if validate_cn_id(number)[0]]
    return (valid or candidates or [""])[0]


def _all_dates(text: str) -> list[str]:
    return [normalize_date(x) for x in re.findall(DATE, text)]


def _education_level(text: str) -> str:
    text = re.sub(r"\s", "", text)
    if any(marker in text for marker in ("本校初中部", "初中部学习", "初中学习", "（初）毕字", "(初)毕字")):
        return "初中"
    if any(marker in text for marker in ("普通高中", "高级中学", "高中毕业", "高中阶段", "（高）毕字", "(高)毕字")):
        return "高中"
    if any(marker in text for marker in ("中等职业学校", "中等专业学校", "职业高中", "职业中学", "技工学校", "技师学院", "中专毕业")):
        return "中职"
    if any(marker in text for marker in ("专升本科", "专科起点本科", "本科层次", "大学本科")):
        return "本科"
    levels = ["博士研究生", "硕士研究生", "研究生", "博士", "硕士", "本科", "高职", "大专", "专科", "中职", "中专", "高中", "初中"]
    for level in levels:
        if level in text:
            return {"博士研究生":"研究生", "硕士研究生":"研究生", "硕士":"研究生", "博士":"研究生", "专科":"大专", "中专":"中职"}.get(level, level)
    return ""


def _education_form(text: str) -> str:
    compact = re.sub(r"\s", "", text)
    forms = [
        ("高等教育自学考试", ("高等教育自学考试", "自学考试委员会", "自考毕业")),
        ("成人高等教育", ("成人高等教育", "成人教育", "函授", "业余学习", "夜大学")),
        ("开放教育", ("开放大学", "开放教育", "广播电视大学")),
        ("网络教育", ("网络教育", "现代远程教育", "远程教育")),
        ("普通高等教育", ("普通高等教育", "普通高校")),
        ("普通高中", ("普通高中", "高级中学")),
        ("中等职业教育", ("中等职业学校", "中等专业学校", "职业高中", "职业中学", "技工学校", "技师学院")),
    ]
    return next((label for label, markers in forms if any(marker in compact for marker in markers)), "")


def _person_name(text: str, expected_person: str) -> str:
    compact = re.sub(r"\s", "", text)
    # 文件夹姓名只用于锁定OCR中实际出现的姓名，不能在未识别时自动补值。
    if expected_person and re.search(
        rf"(?:姓名|学生)[:：]?[，,]?{re.escape(expected_person)}(?=性别|民族|出生|，|,|$)",
        compact,
    ):
        return expected_person
    rejected = {"姓名", "性别", "出生年月", "身份证号", "联系电话", "学生"}
    patterns = [
        r"(?:姓名|学生)\s*[：:]?\s*([\u4e00-\u9fff·]{2,4})(?=\s*(?:性别|民族|出生|，|,|$))",
        r"(?:姓名|学生)\s*[：:]?\s*([\u4e00-\u9fff·]{2,4})",
        r"兹有(?:我单位)?\s*([\u4e00-\u9fff·]{2,4})(?=\s*[（(，,])",
    ]
    for pattern in patterns:
        for value in re.findall(pattern, text):
            value = value.strip()
            if value not in rejected and not any(label in value for label in rejected):
                return value
    return expected_person if expected_person and expected_person in compact else ""


def _school_name(text: str) -> str:
    compact = re.sub(r"[\s_]+", "", text)
    suffix = r"(?:大学|学院|学校|中学|中专|职高)"
    labelled = re.findall(
        rf"(?:毕业院校|毕业学校|院校名称|学校名称|高等院校|校名|学校)[:：]?"
        rf"([\u4e00-\u9fff]{{2,30}}?{suffix})",
        compact,
    )
    general = re.findall(rf"([\u4e00-\u9fff]{{2,30}}?{suffix})", compact)
    rejected = {"本校", "学校", "院校名称", "毕业院校"}
    def cleaned(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            value = re.sub(r"^(?:名称|姓名)", "", value)
            if value not in rejected and not value.startswith(("在本校", "于本校")):
                result.append(value)
        return result

    # “学校名称/毕业院校”等明确标签后的值优先。不能再与页面其他“学院”
    # 文本按长度竞争，否则学信网报告中的“系所 信息工程学院”等字段会覆盖学校名称。
    labelled_values = cleaned(labelled)
    if labelled_values:
        return labelled_values[0]
    values = []
    for value in general:
        value = re.sub(r"^(?:名称|姓名)", "", value)
        if value not in rejected and not value.startswith(("在本校", "于本校")):
            values.append(value)
    return max(values, key=len) if values else ""


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
    ranges = list(re.finditer(rf"({DATE})\s*(?:至今|(?:至|到|—|–|-|~|～)\s*({DATE}))", text))
    records: list[WorkRecord] = []
    for index, date_match in enumerate(ranges):
        company = companies[min(index, len(companies) - 1)] if companies else ""
        if not company:
            continue
        end_raw = date_match.group(2) or "至今"
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


def _form_table_work_records(text: str, material: Material, page_no: int) -> list[WorkRecord]:
    """读取申报表“工作经历”逐行表格，不依赖每行重复打印字段标题。"""
    if material.document_type != "申报表":
        return []
    records: list[WorkRecord] = []
    headers = {
        "工作经历",
        "何年何月至何年何月", "从何年何月开始", "从事何职业",
        "所在单位", "证明人姓名、电话", "证明人姓名电话",
    }
    company_suffixes = (
        "有限公司", "股份有限公司", "有限责任公司", "公司", "企业",
        "中心", "事务所", "合作社", "商行", "商店", "门店", "经营部",
        "工作室", "学校", "医院", "酒店", "宾馆", "厂",
    )
    period_pattern = re.compile(
        rf"({DATE})\s*(?:(至今)|(?:至|到|—|–|-|~|～)\s*({DATE}))"
    )

    def clean_cell(value: str) -> str:
        # Word 表格可能含手工换行、单元格结束标记和零宽字符；PDF/OCR也可能
        # 在年月、公司名称中插入换行。这里仅清除不可见控制符，不改变汉字内容。
        return re.sub(r"[\x00-\x1f\x7f\u200b\ufeff]+", " ", value).strip(" ：:，,")

    def parse_cells(cells: list[str]) -> WorkRecord | None:
        cells = [clean_cell(cell) for cell in cells]
        cells = [cell for cell in cells if cell and re.sub(r"\s", "", cell) not in headers]
        period_index = None
        match = None
        consumed = 1
        for index in range(len(cells)):
            for width in (1, 2, 3):
                combined = "".join(cells[index:index + width])
                candidate = period_pattern.search(combined)
                if candidate:
                    period_index, match, consumed = index, candidate, width
                    break
            if match:
                break
        if period_index is None or not match:
            return None
        tail = cells[period_index + consumed:]
        company_index = None
        company_width = 1
        company_candidates: list[tuple[int, int, str]] = []
        for index in range(len(tail)):
            for width in (1, 2, 3):
                combined = re.sub(r"\s", "", "".join(tail[index:index + width]))
                if combined.endswith(company_suffixes) and combined not in company_suffixes:
                    company_candidates.append((index, width, combined))
        if company_candidates:
            # 优先完整的单个单元格；若公司名被PDF换行拆开，则采用能形成
            # 企业全称的最短连续组合，避免把前一列“物业电工”拼进企业名。
            company_index, company_width, _ = min(company_candidates, key=lambda item: (item[1], item[0]))
        if company_index is None:
            company_index = 1 if len(tail) >= 2 else (0 if tail else None)
        if company_index is None:
            return None
        company = normalize_company("".join(tail[company_index:company_index + company_width]))
        if not company:
            return None
        occupation_values = [
            value for value in tail[:company_index]
            if value not in {"从事何职业", "职业", "工种", "岗位"}
        ]
        occupation = occupation_values[-1] if occupation_values else ""
        witness_text = " ".join(tail[company_index + company_width:])
        phone_match = re.search(r"(?<!\d)(1\d{10}|0\d{2,3}-?\d{7,8})(?!\d)", witness_text)
        witness_phone = re.sub(r"\D", "", phone_match.group(1)) if phone_match else ""
        name_text = witness_text[:phone_match.start()] if phone_match else witness_text
        name_match = re.search(r"([\u4e00-\u9fff·]{2,8})(?:先生|女士)?", name_text)
        witness_name = name_match.group(1) if name_match else ""
        end_raw = match.group(2) or match.group(3)
        return WorkRecord(
            person=material.person,
            company=company,
            start=normalize_date(match.group(1)),
            end="至今" if end_raw == "至今" else normalize_date(end_raw),
            duration_months=None,
            source=f"{material.path.name} 第{page_no}页",
            occupation=occupation,
            source_type="申报表",
            witness_name=witness_name,
            witness_phone=witness_phone,
        )

    in_work_section = False
    for line in text.splitlines():
        raw_cells = [clean_cell(cell) for cell in line.split("\t")]
        cells = [cell for cell in raw_cells if cell and cell not in headers]
        compact_line = re.sub(r"\s", "", line)
        if "工作经历" in compact_line or ("从事何职业" in compact_line and "所在单位" in compact_line):
            in_work_section = True
            # Word 纵向合并的“工作经历”单元格会在每一数据行中重复返回。
            # 只有纯表头行才跳过；同一行若含时间范围，必须继续解析。
            if not period_pattern.search(compact_line):
                continue
        if not in_work_section:
            continue
        record = parse_cells(raw_cells)
        if record:
            records.append(record)
    if records:
        return records

    # PDF文本层/OCR通常不保留表格制表符，而是把一行四个单元格拆成连续行。
    # 从“工作经历”区域开始，将连续文本作为单元格序列重新组合，并按每个时间范围分段。
    lines = [clean_cell(line) for line in text.splitlines() if clean_cell(line)]
    work_start = None
    for index in range(len(lines)):
        rolling = re.sub(r"\s", "", "".join(lines[max(0, index - 3):index + 1]))
        if "工作经历" in rolling or ("从事何职业" in rolling and "所在单位" in rolling):
            work_start = index + 1
            break
    if work_start is None:
        return []
    tokens: list[str] = []
    for line in lines[work_start:]:
        tokens.extend(clean_cell(cell) for cell in line.split("\t") if clean_cell(cell))
    period_starts: list[int] = []
    for index in range(len(tokens)):
        if any(period_pattern.search("".join(tokens[index:index + width])) for width in (1, 2, 3)):
            if not period_starts or index > period_starts[-1] + 2:
                period_starts.append(index)
    for position, start in enumerate(period_starts):
        end = period_starts[position + 1] if position + 1 < len(period_starts) else len(tokens)
        record = parse_cells(tokens[start:end])
        if record:
            records.append(record)
    return records


def _commitment_work_records(text: str, material: Material, page_no: int) -> list[WorkRecord]:
    if material.document_type != "工作年限承诺书":
        return []
    records: list[WorkRecord] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) < 2:
            continue
        period = re.sub(r"\s", "", cells[0])
        match = re.search(r"(\d{4})年(\d{1,2})月至(\d{4})年(\d{1,2})月", period)
        if not match:
            continue
        company = normalize_company(cells[1])
        if not company or company in {"单位名称"}:
            continue
        occupation = cells[3].replace("/", "").strip() if len(cells) > 3 else ""
        records.append(WorkRecord(
            person=material.person,
            company=company,
            start=f"{int(match.group(1)):04d}-{int(match.group(2)):02d}",
            end=f"{int(match.group(3)):04d}-{int(match.group(4)):02d}",
            duration_months=None,
            source=f"{material.path.name} 第{page_no}页",
            occupation=occupation,
            source_type="工作年限承诺书",
        ))
    return records


def _work_proof_record(text: str, material: Material, page_no: int) -> list[WorkRecord]:
    if material.document_type != "工作证明":
        return []
    company = _first([
        r"单位[（(]?盖章[）)]?\s*[：:]?\s*([^\n，,。；;]{2,80})",
        r"(?:单位名称|工作单位)\s*[：:]?\s*([^\n，,。；;]{2,80})",
        r"在\s*([^\n，,。；;]{2,80})\s*[，,]?\s*从事",
    ], text)
    compact_text = re.sub(r"\s", "", text)
    period = re.search(rf"(?:自)?({DATE})(?:至今|(?:至|到|—|–|-)({DATE}))", compact_text)
    occupation = _first([
        r"(?:从事|担任)\s*([^\n，,。；;\d]{1,40}?)(?:职位|岗位)?(?:相关行业)?(?:工作)?\s*\d+(?:\.\d+)?\s*年",
        r"(?:从事|担任)\s*([^\n，,。；;]{1,40}?)(?:相关行业)?工作",
    ], text)
    if not company or not period:
        return []
    return [WorkRecord(material.person, normalize_company(company), normalize_date(period.group(1)), "至今" if period.group(2) is None else normalize_date(period.group(2)), None, f"{material.path.name} 第{page_no}页", occupation=occupation, source_type="工作证明")]


def extract_material(material: Material) -> tuple[list[Evidence], list[WorkRecord]]:
    evidences: list[Evidence] = []
    work: list[WorkRecord] = []
    for page_no, text in enumerate(material.text_pages, 1):
        if not text.strip():
            continue
        id_number = _best_id(text)
        candidates = {
            "姓名": (_person_name(text, material.person), normalize_name),
            "性别": (_first([r"性别\s*[：:]?\s*([男女])"], text), lambda x: x),
            "身份证号": (id_number, normalize_id),
            "出生日期": (_labelled_date(text, ("出生日期", "出生年月", "出生")), normalize_date),
            "毕业院校": (_school_name(text) if material.document_type in {"申报表", "学历证明", "学信网学籍证明", "学信网学历证明"} else "", lambda x: x.strip()),
            "毕业证编码": (_first([r"(?:毕业证书编号|学历证书编号|毕业证编号|毕业证号|证书编号)\s*[：:]?\s*([A-Za-z0-9\-]{6,40})", r"[（(](?:初|高)[）)]毕字[^号\n]{0,20}第?\s*([A-Za-z0-9\-]{6,40})\s*号"], text), lambda x: re.sub(r"\s", "", x).upper()),
            "学位证编码": (_first([r"(?:学位证书编号|学位证编号)\s*[：:]?\s*([A-Za-z0-9\-]{6,40})"], text), lambda x: re.sub(r"\s", "", x).upper()),
            "学历层次": ("" if material.document_type == "申报表" else _education_level(text), lambda x: x),
            "学历形式": (_education_form(text), lambda x: x),
            "学籍状态": (_first([r"(?:学籍状态|状态)\s*[：:]?\s*(在籍|在校|保留学籍|休学|离籍|毕业|结业)"], text), lambda x: x),
            "预计毕业时间": (_first([rf"预计毕业日期\s*[：:]?\s*({DATE})"], text), normalize_date),
            "入学时间": (_first([rf"入学日期\s*[：:]?\s*({DATE})"], text), normalize_date),
            "专业": (_first([r"(?:学科专业|专业)\s*[：:]?\s*([^\n\t，,。；;]{1,50})"], text), lambda x: x.strip()),
            "学制": (_first([r"学制\s*[：:]?\s*([0-9一二三四五六七八九十]+年)"], text), lambda x: x.strip()),
            "在线验证码": (_first([r"在线验证码\s*[：:]?\s*([A-Z0-9]{8,24})"], text), lambda x: re.sub(r"\s", "", x).upper()),
            "获学位时间": (_first([rf"获学位日期\s*[：:]?\s*({DATE})"], text), normalize_date),
            "学位授予单位": (_first([r"学位授予单位\s*[：:]?\s*([^\n\t，,。]{2,50})"], text), lambda x: x.strip()),
            "学位名称": (_first([r"所授学位\s*[：:]?\s*([^\n\t，,。]{2,30})"], text), lambda x: x.strip()),
            "职业名称": (_first([r"职业名称\s*[：:]?\s*(.{1,40}?)(?=\s*(?:工种/职业方向|工种|职业方向|职业技能等级|证书编号|$))"], text) if material.document_type == "职业技能等级证书" else "", lambda x: x.strip()),
            "职业方向": (_first([r"(?:工种/职业方向|工种|职业方向)\s*[：:]?\s*(.{1,40}?)(?=\s*(?:职业技能等级|证书编号|$))"], text) if material.document_type == "职业技能等级证书" else "", lambda x: x.strip()),
            "职业技能等级": (_first([r"职业技能等级\s*[：:]?\s*(.{1,20}?)(?=\s*(?:证书编号|$))"], text) if material.document_type == "职业技能等级证书" else "", lambda x: x.strip()),
            "职业证书编号": (_first([r"(?:职业技能等级证书编号|证书编号|CertificateNo\.)\s*[：:]?\s*([A-Za-z0-9\-]{10,40})"], text) if material.document_type == "职业技能等级证书" else "", lambda x: re.sub(r"\s", "", x).upper()),
            "申报职业": (
                _first([r"申报职业\s*[：:]?\s*([^\n\t，,。；;]{1,40})"], text)
                if material.document_type == "申报表"
                else _first([r"现申请参加\s*([^\n，,。；;()]{1,40})\s*[（(]职业/工种[）)]"], text)
                if material.document_type == "工作年限承诺书"
                else "",
                lambda x: x.strip(),
            ),
            "申报等级": (_first([r"[（(]职业/工种[）)]\s*[_\s]*([1-5一二三四五])[_\s]*级"], text) if material.document_type in {"申报表", "工作年限承诺书"} else "", lambda x: x.strip()),
            "承诺工作年限": (_first([r"工作共\s*(\d+)\s*年"], text), lambda x: str(int(x) * 12)),
            "从事本职业年限": (_first([r"从事本职业年限\s*[：:]?\s*(\d+(?:\.\d+)?)\s*年"], text) if material.document_type == "申报表" else "", lambda x: str(round(float(x) * 12))),
            "证明工作年限": (_first([
                r"(?:工作|任职)\s*(\d+(?:\.\d+)?)\s*年",
                r"从事[^\n，,。；;]{1,40}?(?:职位|岗位)?\s*(\d+(?:\.\d+)?)\s*年",
            ], text) if material.document_type == "工作证明" else "", lambda x: str(round(float(x) * 12))),
            "承诺人签名": (_first([r"(?:考生|本人|承诺人)签名\s*[：:]?\s*([\u4e00-\u9fff·]{2,8})"], text), normalize_name),
            "证明人姓名": (_first([r"(?:部门联系人|联系人)\s*[：:]?\s*([\u4e00-\u9fff·先生女士]{2,12})"], text) if material.document_type == "工作证明" else "", lambda x: x.strip()),
            "证明人电话": (_first([r"(?:联系电话|联系手机|电话)\s*[：:]?\s*(1\d{10}|0\d{2,3}-?\d{7,8})"], text) if material.document_type == "工作证明" else "", lambda x: re.sub(r"\D", "", x)),
            "出具单位": (_first([r"单位[（(]?盖章[）)]?\s*[：:]?\s*([^\n，,。；;]{2,80})"], text), normalize_company),
            "公章状态": ("已检测到红色公章" if "[检测到红色公章]" in text else "", lambda x: x),
            "身份证有效期至": (_first([rf"(?:有效期限|有效期)\s*[：:]?\s*(?:{DATE}\s*[-至]\s*)?({DATE}|长期)"], text), normalize_date),
            "从事职业": (_first([r"(?:职业工种|职业名称)\s*[：:]?\s*([^\n\t，,。；;]{1,30})"], text) if material.document_type == "职业技能等级证书" else "", lambda x: x.strip()),
            "企业名称": (_first([r"(?:企业名称|主体名称|字号名称|名称)\s*[：:]?\s*([^\n\t，,。；;]{2,80})"], text) if material.document_type == "企业信息截图" else "", normalize_company),
            "经营范围": (_first([r"经营范围\s*[：:]?\s*([^\n]{4,500})"], text) if material.document_type == "企业信息截图" else "", lambda x: x.strip()),
        }
        # 普通学历证明以证书页面最后出现的日期作为右下角落款日期。
        dates = _all_dates(text)
        if material.document_type == "学历证明" and dates:
            candidates["毕业时间"] = (dates[-1], normalize_date)
        elif material.document_type == "学信网学籍证明" and candidates["预计毕业时间"][0]:
            # 在籍人员尚未毕业，申报表“毕业时间”按学信网预计毕业日期核验。
            candidates["毕业时间"] = candidates["预计毕业时间"]
        else:
            candidates["毕业时间"] = (_labelled_date(text, ("毕业时间", "毕业日期", "授予日期", "发证日期")), normalize_date)

        for field, (raw, normalizer) in candidates.items():
            if raw:
                evidences.append(Evidence(
                    material.person, material.path.name, page_no,
                    material.document_type, field, raw, normalizer(raw),
                    confidence=material.ocr_confidence,
                ))
        form_records = _form_table_work_records(text, material, page_no)
        work.extend(form_records)
        # 非表格式材料或未命中表格时，保留原有“带字段标签”解析。
        if not form_records:
            work.extend(_work_records(text, material, page_no))
        work.extend(_commitment_work_records(text, material, page_no))
        work.extend(_work_proof_record(text, material, page_no))
    material.evidences = evidences
    return evidences, work
