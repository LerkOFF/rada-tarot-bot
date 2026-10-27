import random
from datetime import date

from rada import deck, library, numerology


def test_library_complete():
    assert library.has_cards()
    for c in deck.DECK:
        for rev in (False, True):
            card = deck.Card(c.slug, c.name, rev)
            assert library.daily(card) and library.yesno(card) and library.core(card)
    for n in range(22):
        assert library.arcana(n)["text"] and library.year(n) and library.pair(n)


def test_spread_fallback_three_and_five():
    for n in (3, 5):
        cards = deck.draw(n, random.Random(n))
        text = library.spread_text("вопрос", cards)
        assert text and cards[0].title in text
        assert text.count(":") >= n
    assert "Прошлое:" in library.spread_text("в", deck.draw(3, random.Random(1)))
    assert "Итог:" in library.spread_text("в", deck.draw(5, random.Random(1)))


def test_spread_is_deterministic_for_same_cards():
    cards = deck.draw(3, random.Random(7))
    assert library.spread_text("a", cards) == library.spread_text("b", cards)


def test_followup_and_full_fallback():
    cards = deck.draw(3, random.Random(2))
    assert "Вернись к карте" in library.followup_text(cards, "а что с работой")
    birth = date(1990, 1, 1)
    n = numerology.arcana_of(birth)
    text = library.full_text("Аня", n, numerology.year_card(birth, 2026), 2026)
    assert "Мир" in text and "Напутствие" in text and "Аня" in text


def test_no_long_dash_anywhere():
    blob = "".join(p.read_text(encoding="utf-8") for p in library.LIB_DIR.glob("*.json"))
    assert "—" not in blob and "–" not in blob
