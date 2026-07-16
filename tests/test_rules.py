import unittest
from pathlib import Path

from verifier.company import CompanyRegistry
from verifier.config import AppConfig
from verifier.idcard import birthday_from_id, validate_cn_id
from verifier.models import Evidence, Material, WorkRecord
from verifier.normalize import duration_months, format_year_month, normalize_date
from verifier.rules import evaluate


def material(person, filename, kind, evidences=()):
    value = Material(person, Path(filename), kind)
    value.evidences = list(evidences)
    return value


def evidence(person, filename, kind, field, raw, normalized=None):
    return Evidence(person, filename, 1, kind, field, raw, normalized if normalized is not None else raw)


class RuleTests(unittest.TestCase):
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
