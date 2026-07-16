from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QualityConfig:
    min_width: int = 900
    min_height: int = 550
    blur_variance_min: float = 70.0
    glare_ratio_max: float = 0.12
    glare_largest_region_ratio_max: float = 0.055
    severe_rotation_degrees: float = 12.0


@dataclass
class AppConfig:
    quality: QualityConfig = field(default_factory=QualityConfig)
    supported_extensions: tuple[str, ...] = (
        ".docx", ".pdf", ".jpg", ".jpeg", ".png"
    )
    image_dpi: int = 240
    ocr_language: str = "chi_sim+eng"
    require_company_registry: bool = False
    functional_positions: tuple[str, ...] = (
        "人事", "人力资源", "行政", "财务", "会计", "出纳", "经理",
        "总经理", "项目管理", "办公室", "文员", "法务", "采购", "销售",
    )
    occupation_scope_keywords: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "电工": ("电气", "电力", "机电", "设备安装", "维修"),
        "焊工": ("焊接", "金属", "机械制造", "设备制造"),
        "保育师": ("托育", "保育", "幼儿", "儿童"),
        "养老护理": ("养老", "护理", "老年人"),
        "育婴": ("母婴", "婴幼儿", "家政"),
        "电子商务": ("电子商务", "互联网销售", "网络销售"),
        "美容": ("美容", "美发", "化妆"),
        "茶艺": ("茶叶", "茶艺", "餐饮"),
    })
