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

