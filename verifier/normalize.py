from __future__ import annotations

import re
from datetime import date


def compact(value: str) -> str:
    return re.sub(r"[\s　]+", "", value or "").strip("：:，,。.;；")


def normalize_date(value: str) -> str:
    value = compact(value)
    chinese_digits = {"〇": "0", "零": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
    cm = re.search(r"([〇零一二三四五六七八九]{4})年([一二三四五六七八九十]{1,3})月(?:([一二三四五六七八九十]{1,3})日)?", value)
    if cm:
        year = int("".join(chinese_digits[x] for x in cm.group(1)))
        def cn_num(s: str | None) -> int | None:
            if not s: return None
            nums = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
            if s == "十": return 10
            if "十" in s:
                a, b = s.split("十", 1)
                return (nums.get(a, 1) * 10) + nums.get(b, 0)
            return nums.get(s)
        mo, day = cn_num(cm.group(2)), cn_num(cm.group(3))
        if mo and 1 <= mo <= 12:
            if day:
                try: return date(year, mo, day).isoformat()
                except ValueError: return value
            return f"{year:04d}-{mo:02d}"
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


def format_year_month(value: str) -> str:
    n = normalize_date(value)
    m = re.match(r"(\d{4})-(\d{2})", n)
    return f"{int(m.group(1))}.{int(m.group(2))}" if m else value


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
