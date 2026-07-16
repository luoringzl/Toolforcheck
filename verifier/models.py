from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Evidence:
    person: str
    file: str
    page: int
    document_type: str
    field: str
    raw_value: str
    normalized_value: str = ""
    confidence: float | None = None


@dataclass
class Material:
    person: str
    path: Path
    document_type: str
    text_pages: list[str] = field(default_factory=list)
    quality_status: str = "合格"
    quality_reasons: list[str] = field(default_factory=list)
    evidences: list[Evidence] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    selected_as_basis: bool = False


@dataclass
class Finding:
    person: str
    category: str
    field: str
    status: str
    message: str
    values: str = ""
    sources: str = ""


@dataclass
class WorkRecord:
    person: str
    company: str
    start: str
    end: str
    duration_months: int | None
    source: str
    company_status: str = ""
    company_message: str = ""
    occupation: str = ""
    business_scope: str = ""
    source_type: str = ""
    witness_name: str = ""
    witness_phone: str = ""


@dataclass
class PersonResult:
    person: str
    materials: list[Material] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    work_records: list[WorkRecord] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
