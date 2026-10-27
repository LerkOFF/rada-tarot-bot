"""Колода Таро: 78 карт, вытягивание, перевёрнутые."""
import random
from dataclasses import dataclass

MAJORS = [
    "Шут", "Маг", "Верховная Жрица", "Императрица", "Император", "Иерофант",
    "Влюблённые", "Колесница", "Сила", "Отшельник", "Колесо Фортуны",
    "Справедливость", "Повешенный", "Смерть", "Умеренность", "Дьявол",
    "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир",
]
ROMAN = [
    "0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
    "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI",
]
SUITS = [("w", "Жезлов"), ("c", "Кубков"), ("s", "Мечей"), ("p", "Пентаклей")]
RANKS = [
    "Туз", "Двойка", "Тройка", "Четвёрка", "Пятёрка", "Шестёрка", "Семёрка",
    "Восьмёрка", "Девятка", "Десятка", "Паж", "Рыцарь", "Королева", "Король",
]
REVERSED_CHANCE = 0.3


@dataclass(frozen=True)
class Card:
    slug: str          # m00..m21, w01..w14, c.., s.., p..
    name: str          # «Король Мечей»
    reversed: bool = False

    @property
    def title(self) -> str:
        return f"{self.name} ({'перевёрнутая' if self.reversed else 'прямая'})"

    @property
    def is_major(self) -> bool:
        return self.slug.startswith("m")


def major(n: int, reversed: bool = False) -> Card:
    return Card(f"m{n:02d}", MAJORS[n], reversed)


def build_deck() -> list:
    deck = [major(i) for i in range(22)]
    for letter, suit in SUITS:
        for i, rank in enumerate(RANKS, start=1):
            deck.append(Card(f"{letter}{i:02d}", f"{rank} {suit}"))
    return deck


DECK = build_deck()
BY_SLUG = {c.slug: c for c in DECK}


def draw(n: int, rng: random.Random = None) -> list:
    rng = rng or random.Random()
    return [Card(c.slug, c.name, rng.random() < REVERSED_CHANCE) for c in rng.sample(DECK, n)]


def card_of_day(user_id: int, day: str) -> Card:
    """Одна и та же карта у человека в течение суток."""
    return draw(1, random.Random(f"{user_id}:{day}"))[0]


def yes_no(card: Card) -> str:
    return "НЕТ" if card.reversed else "ДА"


def card_to_str(card: Card) -> str:
    return f"{card.slug}{'r' if card.reversed else ''}"


def card_from_str(s: str) -> Card:
    rev = s.endswith("r")
    base = BY_SLUG[s[:-1] if rev else s]
    return Card(base.slug, base.name, rev)
