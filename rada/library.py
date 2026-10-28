"""Готовые толкования из data/library/*.json: работают без нейросети и без ключей."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from . import content
from .config import ROOT
from .deck import MAJORS, Card

LIB_DIR = ROOT / "data" / "library"
POSITIONS = {
    3: ["Прошлое", "Настоящее", "Будущее"],
    5: ["Суть вопроса", "Что мешает", "На что опереться", "Ближайшее будущее", "Итог"],
}
INTROS = [
    "Раскладываю карты и слушаю, что они скажут.",
    "Карты легли, и вот что они шепчут.",
    "Смотрю на расклад внимательно, по порядку.",
]
OUTROS = [
    "Карты показывают тенденции, а не приговор: решение всё равно за тобой. Выбери один маленький шаг и сделай его сегодня.",
    "Всё, что здесь сказано, подсказка, а не предопределённость. Прислушайся к той карте, что откликнулась сильнее всего, и начни с неё.",
    "Дорога складывается из твоих шагов. Если что-то в раскладе зацепило, вернись к этой карте и спроси себя, что она просит изменить.",
]


@lru_cache(maxsize=1)
def _cards() -> dict:
    data = {}
    for p in sorted(LIB_DIR.glob("cards_*.json")):
        data.update(json.loads(p.read_text(encoding="utf-8")))
    return data


def _load(name: str):
    p = LIB_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@lru_cache(maxsize=1)
def _arcana() -> dict:
    return _load("arcana.json")


@lru_cache(maxsize=1)
def _year() -> dict:
    return _load("year.json")


@lru_cache(maxsize=1)
def _pair() -> dict:
    return _load("pair.json")


def reload() -> None:
    for f in (_cards, _arcana, _year, _pair):
        f.cache_clear()


ARCANA_FIELDS = ("epigraph", "power", "blind", "decision", "quote", "text")


def _entry(card: Card):
    """Толкование карты с правками из админки (ключи lib.card.<slug>.<up|rev>.<поле>)."""
    e = _cards().get(card.slug)
    if not e:
        return None
    pos = "rev" if card.reversed else "up"
    return {f: content.lib(f"lib.card.{card.slug}.{pos}.{f}", v) for f, v in e[pos].items()}


def defaults_card(slug: str) -> dict:
    return _cards().get(slug) or {}


def defaults_arcana(n: int) -> dict:
    return _arcana().get(str(n)) or {}


def defaults_year(n: int) -> str:
    return _year().get(str(n)) or ""


def defaults_pair(n: int) -> str:
    return _pair().get(str(n)) or ""


def intros() -> list:
    return [x for x in content.lib("lib.intros", "\n".join(INTROS)).splitlines() if x.strip()] or INTROS


def outros() -> list:
    return [x for x in content.lib("lib.outros", "\n".join(OUTROS)).splitlines() if x.strip()] or OUTROS


def has_cards() -> bool:
    return len(_cards()) == 78


def daily(card: Card):
    e = _entry(card)
    return e["day"] if e else None


def yesno(card: Card):
    e = _entry(card)
    return e["yesno"] if e else None


def core(card: Card):
    e = _entry(card)
    return e["core"] if e else None


def arcana(n: int):
    e = _arcana().get(str(n))
    if not e:
        return None
    return {f: content.lib(f"lib.arcana.{n}.{f}", v) for f, v in e.items()}


def year(n: int):
    e = _year().get(str(n))
    return content.lib(f"lib.year.{n}", e) if e else None


def pair(n: int):
    e = _pair().get(str(n))
    return content.lib(f"lib.pair.{n}", e) if e else None


def _pick(items: list, cards: list):
    key = "|".join(f"{c.slug}{int(c.reversed)}" for c in cards)
    return items[int(hashlib.md5(key.encode()).hexdigest(), 16) % len(items)]


def spread_text(question: str, cards: list):
    """Расклад из готовых текстов: позиция, карта, суть. None, если библиотеки нет."""
    if not has_cards():
        return None
    labels = POSITIONS.get(len(cards), [f"Карта {i}" for i in range(1, len(cards) + 1)])
    parts = [_pick(intros(), cards), ""]
    for label, card in zip(labels, cards):
        parts.append(f"{label}: {card.title}")
        parts.append(core(card))
        parts.append("")
    parts.append(_pick(outros(), cards))
    return "\n".join(parts)


def followup_text(cards: list, user_text: str):
    """Уточнение без нейросети: возвращаем к карте, самой близкой по слову, иначе к первой."""
    if not has_cards():
        return None
    words = {w.lower().strip(".,!?«»") for w in user_text.split() if len(w) > 3}
    best = cards[0]
    for c in cards:
        if any(w in (core(c) or "").lower() for w in words):
            best = c
            break
    return (f"Вернись к карте «{best.name}» ({'перевёрнутая' if best.reversed else 'прямая'}): "
            f"{core(best)} Спроси себя, как это связано с тем, о чём ты сейчас думаешь, "
            "и что эта карта просит сделать первым.")


def full_text(name: str, n: int, year_n: int, year_num: int):
    a, y = arcana(n), year(year_n)
    if not a or not y:
        return None
    who = f"{name}, " if name else ""
    return "\n".join([
        f"Полный разбор судьбы: {MAJORS[n]}",
        "",
        "Характер и дорога",
        a["text"],
        "",
        "Твоя сила",
        a["power"] + ".",
        "",
        "Слепая зона",
        a["blind"] + ". Замечать её уже половина работы.",
        "",
        "Как ты принимаешь решения",
        a["decision"] + ".",
        "",
        f"Ближайший год ({MAJORS[year_n]})",
        y,
        "",
        "Напутствие",
        f"{who}{a['quote']}".strip(),
    ])
