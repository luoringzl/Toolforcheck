from __future__ import annotations

from .normalize import normalize_company

ORG_SUFFIXES = (
    "有限责任公司", "股份有限公司", "有限公司", "集团有限公司",
    "合伙企业", "个人独资企业", "分公司", "支公司", "事务所",
    "研究院", "事业单位", "社会团体",
    "合作社", "经营部", "工作室", "商行", "商店", "门店", "甜品店",
    "蛋糕店", "酒店", "宾馆", "医院", "学校", "中心", "厂",
)


class CompanyRegistry:
    """仅检查明显简称；工商登记全称以人员提交的企业信息截图为准。"""

    @staticmethod
    def looks_full(name: str) -> bool:
        n = normalize_company(name)
        return len(n) >= 6 and any(n.endswith(s) for s in ORG_SUFFIXES)

    def validate(self, name: str) -> tuple[str, str]:
        n = normalize_company(name)
        if not self.looks_full(n):
            return "退回", "该企业信息为简称，请补充与工商信息一致的全称"
        return "通过", "名称形式完整；工商登记全称以企业信息截图核对结果为准"

