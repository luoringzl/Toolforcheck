import unittest
from pathlib import Path

from verifier.company import CompanyRegistry
from verifier.idcard import birthday_from_id, validate_cn_id
from verifier.models import Evidence, Material
from verifier.normalize import duration_months, normalize_date
from verifier.rules import evaluate


class RuleTests(unittest.TestCase):
    def test_dates_and_duration(self):
        self.assertEqual(normalize_date("2020年3月"), "2020-03")
        self.assertEqual(normalize_date("2020.03.15"), "2020-03-15")
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

    def test_inconsistent_name(self):
        material = Material("张三", Path("简历.docx"), "简历")
        evidences = [
            Evidence("张三", "身份证.jpg", 1, "身份证", "姓名", "张三", "张三"),
            Evidence("张三", "简历.docx", 1, "简历", "姓名", "张山", "张山"),
        ]
        result = evaluate("张三", [material], evidences, [], CompanyRegistry())
        self.assertTrue(any(f.field == "姓名" and f.status == "不一致" for f in result.findings))


if __name__ == "__main__":
    unittest.main()
