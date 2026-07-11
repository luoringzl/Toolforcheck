from __future__ import annotations

import re
from datetime import date


def compact(value: str) -> str:
    return re.sub(r"[\s　]+", "", value or "").strip("：:，,。.;；")


def normalize_date(value: str) -> str:
    value = compact(value)
    patterns = [
        r"(?P<y>19\d{2}|20\d{2})[年./\-](?P<m>\d{1,2})(?:[月./\-](?P<d>\d{1,2})日?)?",
        r"(?P<y>19\d{2}|20\d{2})(?P<m>\d{2})(?P<d>\d{2})",
    ]
    for p in patterns:
        m = re.search(p, value)
        if m:
            y, mo = int(m.group("y")), int(m.group("m"))
            d = m.groupdict().get("d")
            if not 1 <= mo <= 12:
                return value
            if d:
                try:
                    return date(y, mo, int(d)).isoformat()
                except ValueError:
                    return value
            return f"{y:04d}-{mo:02d}"
    return value


def normalize_id(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def normalize_name(value: str) -> str:
    return compact(value).replace("·", "")


def normalize_company(value: str) -> str:
    return compact(value).replace("（", "(").replace("）", ")")


def month_index(value: str) -> int | None:
    n = normalize_date(value)
    m = re.match(r"(\d{4})-(\d{2})", n)
    return int(m.group(1)) * 12 + int(m.group(2)) - 1 if m else None


def duration_months(start: str, end: str) -> int | None:
    a, b = month_index(start), month_index(end)
    if a is None or b is None or b < a:
        return None
    return b - a + 1

