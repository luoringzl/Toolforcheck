import unittest
from pathlib import Path

from verifier.company import CompanyRegistry
from verifier.config import AppConfig
from verifier.idcard import birthday_from_id, validate_cn_id
from verifier.models import Evidence, Material, WorkRecord
from verifier.normalize import duration_months, format_year_month, normalize_date
from verifier.rules import evaluate
from verifier.readers import classify_document, refine_document_type
from verifier.extract import extract_material


def material(person, filename, kind, evidences=()):
    value = Material(person, Path(filename), kind)
    value.evidences = list(evidences)
    return value


def evidence(person, filename, kind, field, raw, normalized=None):
    return Evidence(person, filename, 1, kind, field, raw, normalized if normalized is not None else raw)


class RuleTests(unittest.TestCase):
    def test_junior_high_diploma_recognition(self):
        self.assertEqual(classify_document(Path("陈俊顺学历.jpg")), "学历证明")
        self.assertEqual(classify_document(Path("黄苗可毕业证书.jpg")), "学历证明")
        ocr_text = "学生 陈俊顺，于二〇二一年九月至二〇二四年七月 在本校初中部学习，学制叁年，修业期满，成绩合格，准予毕业。（初）毕字（24）第08150197号 二〇二四年七月十五日"
        self.assertEqual(refine_document_type("其他材料", ocr_text), "学历证明")
        diploma = Material("陈俊顺", Path("材料1.jpg"), refine_document_type("其他材料", ocr_text))
        diploma.text_pages = [ocr_text]
        evidences, _ = extract_material(diploma)
        level = next(e.normalized_value for e in evidences if e.field == "学历层次")
        self.assertEqual(level, "初中")

    def test_company_registry_screenshot_recognition(self):
        company_page = "企业名称 福州德鲁伊文化传媒有限公司 统一社会信用代码 91350100MABQNX33XG 经营状态 注销 成立日期 2022-06-16 登记机关 福州市市场监督管理局 经营范围 文艺创作；软件开发"
        sole_trader_page = "工商信息 名称 福州市鼓楼区美日甜甜品店 经营者 蔡艺萱 登记状态 存续 统一社会信用代码 92350102MABXEFRX6L 企业类型 个体工商户 登记机关 福州市鼓楼区市场监督管理局 经营范围 餐饮服务；食品销售"
        self.assertEqual(classify_document(Path("22.png")), "其他材料")
        self.assertEqual(refine_document_type("其他材料", company_page), "企业信息截图")
        self.assertEqual(refine_document_type("其他材料", sole_trader_page), "企业信息截图")

    def test_high_school_and_bachelor_diplomas(self):
        high_school = "普通高中毕业证书 学生彭思敏 自二〇一八年九月至二〇二一年七月在本校修业期满，成绩合格，准予毕业。学校：三合中学 毕业证号：20210827040385 二〇二一年七月十日"
        bachelor = "毕业证书 学生陈璐 于2007年1月至2010年1月在本校英语专业业余学习，修完三年制专升本科教学计划规定的全部课程，成绩合格，准予毕业。校名：漳州师范学院 证书编号：104025201005000449"
        self_study = "高等教育自学考试毕业证书 姓名庄艳华 参加人力资源管理专业本科高等教育自学考试，全部课程成绩合格，经审定，准予毕业。高等院校：福建师范大学 证书编号65359101211143622"
        for content, expected_level in ((high_school, "高中"), (bachelor, "本科"), (self_study, "本科")):
            diploma = Material("测试", Path("毕业证书.jpg"), refine_document_type("其他材料", content))
            diploma.text_pages = [content]
            evidences, _ = extract_material(diploma)
            self.assertEqual(diploma.document_type, "学历证明")
            self.assertEqual(next(e.normalized_value for e in evidences if e.field == "学历层次"), expected_level)
        self_study_diploma = Material("测试", Path("毕业证书.pdf"), "学历证明")
        self_study_diploma.text_pages = [self_study]
        evidences, _ = extract_material(self_study_diploma)
        self.assertEqual(next(e.normalized_value for e in evidences if e.field == "学历形式"), "高等教育自学考试")

    def test_chsi_subtypes_and_skill_certificate(self):
        student = "教育部学籍在线验证报告 学校名称 福建农业职业技术学院 层次 专科 学籍状态 在籍（注册学籍） 入学日期 2024年09月08日 预计毕业日期 2027年06月26日 在线验证码 ARTJPH2ZKNDQ22CK"
        degree = "中国高等教育学位在线验证报告 学位授予单位 福建师范大学 所授学位 艺术学学士学位 获学位日期 2019年06月17日 学位证书编号 1039442019003115"
        skill = "职业技能等级证书 姓名 吴海娟 职业名称 互联网营销师 工种/职业方向 平台管理员 职业技能等级 三级/高级工 证书编号 S000035001051243000362"
        self.assertEqual(refine_document_type("其他材料", student), "学信网学籍证明")
        self.assertEqual(refine_document_type("学历证明", degree), "学信网学位证明")
        self.assertEqual(refine_document_type("其他材料", skill), "职业技能等级证书")
        m = Material("吴海娟", Path("证书.jpg"), "职业技能等级证书")
        m.text_pages = [skill]
        evidences, _ = extract_material(m)
        fields = {e.field: e.normalized_value for e in evidences}
        self.assertEqual(fields["职业名称"], "互联网营销师")
        self.assertEqual(fields["职业技能等级"], "三级/高级工")
        self.assertEqual(fields["职业证书编号"], "S000035001051243000362")

    def test_commitment_word_table_and_month_total(self):
        text = "工作年限承诺书\n姓名: 彭思敏，现申请参加 公共营养师 (职业/工种)_4__级职业技能等级认定，从事本职业或相关职业工作共5年，工作经历如下：\n2021年8月至2022年12月\t皇冠蛋糕店\t遂川县\t西点裱花师\n2023年2月至2026年5月\t可斯贝莉门店\t泉州市\t西点裱花师\n2026年6月至2026年7月\t福州市鼓楼区美日甜甜品店\t福州市\t西点裱花师\n考生签名：彭思敏"
        m = Material("彭思敏", Path("工作年限承诺书.docx"), "工作年限承诺书")
        m.text_pages = [text]
        evidences, records = extract_material(m)
        self.assertEqual(len(records), 3)
        self.assertEqual(sum(duration_months(w.start, w.end) or 0 for w in records), 59)
        fields = {e.field: e.normalized_value for e in evidences}
        self.assertEqual(fields["承诺工作年限"], "60")
        self.assertEqual(fields["承诺人签名"], "彭思敏")

    def test_dates_chinese_and_duration(self):
        self.assertEqual(normalize_date("2020年3月"), "2020-03")
        self.assertEqual(normalize_date("二〇二〇年七月"), "2020-07")
        self.assertEqual(normalize_date("二零二零年七月十五日"), "2020-07-15")
        self.assertEqual(format_year_month("2018-07-07"), "2018.7")
        self.assertEqual(duration_months("2020-03", "2021-02"), 12)

    def test_id_validation(self):
        ok, reasons = validate_cn_id("11010519491231002X")
        self.assertTrue(ok)
        self.assertFalse(reasons)
        self.assertEqual(birthday_from_id("11010519491231002X"), "1949-12-31")

    def test_company_hard_rule(self):
        registry = CompanyRegistry()
        self.assertEqual(registry.validate("腾讯")[0], "退回")
        self.assertIn("简称", registry.validate("腾讯公司")[1])
        self.assertEqual(registry.validate("深圳市腾讯计算机系统有限公司")[0], "待复核")

    def test_form_identity_mismatch(self):
        person = "张三"
        identity_evidence = [
            evidence(person, "身份证.jpg", "身份证", "姓名", "张三"),
            evidence(person, "身份证.jpg", "身份证", "身份证号", "11010519491231002X"),
            evidence(person, "身份证.jpg", "身份证", "身份证有效期至", "长期"),
        ]
        form_evidence = [
            evidence(person, "申报表.docx", "申报表", "姓名", "张山"),
            evidence(person, "申报表.docx", "申报表", "身份证号", "11010519491231002X"),
        ]
        materials = [
            material(person, "身份证.jpg", "身份证", identity_evidence),
            material(person, "申报表.docx", "申报表", form_evidence),
            material(person, "证件照.jpg", "证件照"),
            material(person, "毕业证.jpg", "学历证明"),
        ]
        result = evaluate(person, materials, identity_evidence + form_evidence, [], CompanyRegistry())
        self.assertTrue(any(f.field == "姓名" and f.status == "不一致" for f in result.findings))

    def test_two_jobs_need_commitment_and_no_overlap(self):
        person = "李四"
        identity_evidence = [
            evidence(person, "身份证.jpg", "身份证", "身份证号", "11010519491231002X"),
            evidence(person, "身份证.jpg", "身份证", "身份证有效期至", "长期"),
        ]
        form = material(person, "申报表.docx", "申报表")
        identity = material(person, "身份证.jpg", "身份证", identity_evidence)
        jobs = [
            WorkRecord(person, "北京示例科技有限公司", "2020-01", "2021-06", None, "申报表 第1页", source_type="申报表"),
            WorkRecord(person, "上海示例科技有限公司", "2021-06", "2022-12", None, "申报表 第1页", source_type="申报表"),
        ]
        materials = [form, identity, material(person, "证件照.jpg", "证件照"), material(person, "毕业证.jpg", "学历证明"), material(person, "工作证明.jpg", "工作证明"), material(person, "企业1.png", "企业信息截图"), material(person, "企业2.png", "企业信息截图")]
        result = evaluate(person, materials, identity_evidence, jobs, CompanyRegistry(), AppConfig())
        self.assertTrue(any(f.field == "工作年限承诺书" and f.status == "缺少材料" for f in result.findings))
        self.assertTrue(any(f.field == "工作经历重叠" and f.status == "不一致" for f in result.findings))

    def test_work_gap_is_allowed(self):
        person = "王五"
        jobs = [
            WorkRecord(person, "甲有限公司", "2020-01", "2020-06", None, "表", source_type="申报表"),
            WorkRecord(person, "乙有限公司", "2021-01", "2021-06", None, "表", source_type="申报表"),
        ]
        result = evaluate(person, [], [], jobs, CompanyRegistry())
        self.assertFalse(any(f.field == "工作经历重叠" for f in result.findings))


if __name__ == "__main__":
    unittest.main()
