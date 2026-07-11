from __future__ import annotations

from datetime import date

WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
CHECK = "10X98765432"


def validate_cn_id(number: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    n = number.strip().upper()
    if len(n) != 18 or not n[:17].isdigit() or n[-1] not in "0123456789X":
        return False, ["身份证号码不是合法的18位格式"]
    birthday = n[6:14]
    try:
        date(int(birthday[:4]), int(birthday[4:6]), int(birthday[6:8]))
    except ValueError:
        reasons.append("身份证号码中的出生日期无效")
    expected = CHECK[sum(int(x) * w for x, w in zip(n[:17], WEIGHTS)) % 11]
    if n[-1] != expected:
        reasons.append("身份证号码校验位错误")
    return not reasons, reasons


def birthday_from_id(number: str) -> str:
    n = number.strip().upper()
    return f"{n[6:10]}-{n[10:12]}-{n[12:14]}" if len(n) == 18 else ""


def gender_from_id(number: str) -> str:
    n = number.strip().upper()
    if len(n) != 18 or not n[16].isdigit():
        return ""
    return "男" if int(n[16]) % 2 else "女"

