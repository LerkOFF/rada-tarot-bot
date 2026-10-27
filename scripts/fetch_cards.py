"""Скачивает карты Райдера-Уэйта (1909, общественное достояние) с Wikimedia Commons в assets/cards.
Запуск: .venv/bin/python scripts/fetch_cards.py   (78 файлов по ~60-100 КБ, около 6 МБ)"""
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "cards"
MAJORS = ["Fool", "Magician", "High_Priestess", "Empress", "Emperor", "Hierophant", "Lovers", "Chariot",
          "Strength", "Hermit", "Wheel_of_Fortune", "Justice", "Hanged_Man", "Death", "Temperance",
          "Devil", "Tower", "Star", "Moon", "Sun", "Judgement", "World"]
SUITS = {"w": "Wands", "c": "Cups", "s": "Swords", "p": "Pents"}


def names():
    for i, n in enumerate(MAJORS):
        yield f"m{i:02d}", f"RWS_Tarot_{i:02d}_{n}.jpg"
    for letter, suit in SUITS.items():
        for i in range(1, 15):
            yield f"{letter}{i:02d}", f"{suit}{i:02d}.jpg"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    for slug, name in names():
        dest = OUT / f"{slug}.jpg"
        if dest.exists():
            continue
        url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(name) + "?width=600"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rada-tarot-bot/1.0"})
            dest.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            failed.append((slug, name, str(e)))
        time.sleep(0.4)
    print("готово, не скачались:", failed or "нет")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
