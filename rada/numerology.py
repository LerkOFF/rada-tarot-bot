"""Аркан по дате рождения, карта года, аркан пары."""
import re
from datetime import date

DATE_RE = re.compile(r"^\s*(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{4})\s*$")


def parse_date(text: str):
    m = DATE_RE.match(text or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        parsed = date(y, mo, d)
    except ValueError:
        return None
    if parsed > date.today() or y < 1900:
        return None
    return parsed


def _digits(n: int) -> int:
    return sum(int(c) for c in str(n))


def reduce_arcana(n: int) -> int:
    """Сворачиваем до 1..22; 22 это Шут (0)."""
    while n > 22:
        n = _digits(n)
    return 0 if n == 22 else n


def arcana_of(birth: date) -> int:
    return reduce_arcana(_digits(birth.day) + _digits(birth.month) + _digits(birth.year))


def year_card(birth: date, year: int) -> int:
    return reduce_arcana(_digits(birth.day) + _digits(birth.month) + _digits(year))


def pair_arcana(a: date, b: date) -> int:
    return reduce_arcana(arcana_raw(a) + arcana_raw(b))


def arcana_raw(birth: date) -> int:
    n = _digits(birth.day) + _digits(birth.month) + _digits(birth.year)
    while n > 22:
        n = _digits(n)
    return n
