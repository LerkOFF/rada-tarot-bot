"""Проверка data/library: структура, длины, запрещённые символы, повторы зачинов.
Запуск: .venv/bin/python scripts/check_library.py   (код выхода 1, если есть ошибки)"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rada import deck  # noqa: E402

LIB = Path(__file__).resolve().parent.parent / "data" / "library"
BAD_CHARS = re.compile(r"[—–*#_`\[\]{}<>]|[\U0001F000-\U0001FAFF☀-➿]")
TIME_WORDS = re.compile(r"\b(сегодня|сейчас|завтра|вчера)\b", re.I)
YESNO_WORDS = re.compile(r"\b(да|нет)\b", re.I)
DIGIT_YEAR = re.compile(r"\b(19|20)\d\d\b")
LIMITS = {"day": (30, 60), "yesno": (16, 40), "core": (14, 32)}
errors, warns = [], []


def words(s):
    return len(s.split())


def check_text(where, text, lo, hi):
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{where}: пусто")
        return
    if "\n" in text:
        errors.append(f"{where}: перенос строки")
    if BAD_CHARS.search(text):
        errors.append(f"{where}: запрещённый символ {BAD_CHARS.search(text).group(0)!r}")
    if not re.search(r"[а-яё]", text, re.I):
        errors.append(f"{where}: нет кириллицы")
    if not lo <= words(text) <= hi:
        errors.append(f"{where}: {words(text)} слов, нужно {lo}-{hi}")


def main():
    cards = {}
    for p in sorted(LIB.glob("cards_*.json")):
        cards.update(json.loads(p.read_text(encoding="utf-8")))
    want = {c.slug for c in deck.DECK}
    if set(cards) != want:
        errors.append(f"карты: нет {sorted(want - set(cards))}, лишние {sorted(set(cards) - want)}")
    openings = Counter()
    for slug, e in cards.items():
        for pos in ("up", "rev"):
            for field, (lo, hi) in LIMITS.items():
                text = e.get(pos, {}).get(field)
                check_text(f"{slug}.{pos}.{field}", text, lo, hi)
                if not isinstance(text, str):
                    continue
                if field == "core" and TIME_WORDS.search(text):
                    errors.append(f"{slug}.{pos}.core: слово времени")
                if field == "yesno" and YESNO_WORDS.search(text):
                    warns.append(f"{slug}.{pos}.yesno: слова да/нет")
                if field == "day":
                    openings[" ".join(text.split()[:2]).lower()] += 1
    arcana = json.loads((LIB / "arcana.json").read_text(encoding="utf-8"))
    for n in range(22):
        e = arcana.get(str(n), {})
        for field, (lo, hi) in {"epigraph": (10, 30), "power": (3, 10), "blind": (3, 11),
                                "decision": (3, 11), "quote": (4, 13), "text": (50, 95)}.items():
            check_text(f"arcana.{n}.{field}", e.get(field), lo, hi)
    for name, (lo, hi) in (("year", (55, 100)), ("pair", (50, 95))):
        d = json.loads((LIB / f"{name}.json").read_text(encoding="utf-8"))
        if sorted(d, key=int) != [str(i) for i in range(22)]:
            errors.append(f"{name}: ключи не 0..21")
        for k, text in d.items():
            check_text(f"{name}.{k}", text, lo, hi)
            if isinstance(text, str) and DIGIT_YEAR.search(text):
                errors.append(f"{name}.{k}: цифра года")
    for opening, cnt in openings.most_common(5):
        if cnt > 6:
            warns.append(f"зачин карты дня «{opening}» повторяется {cnt} раз")
    print(f"карт: {len(cards)}, ошибок: {len(errors)}, замечаний: {len(warns)}")
    for line in errors[:60]:
        print("ОШИБКА", line)
    for line in warns[:30]:
        print("замечание", line)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
