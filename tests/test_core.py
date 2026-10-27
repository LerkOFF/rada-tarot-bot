import random
import time
from datetime import date

from rada import deck, numerology
from rada.db import DB
from rada.llm import parse_json_block


def test_numerology_matches_original_bot():
    a, b = date(1990, 1, 1), date(1991, 2, 2)
    assert deck.MAJORS[numerology.arcana_of(a)] == "Мир"
    assert deck.MAJORS[numerology.year_card(a, 2026)] == "Повешенный"
    assert deck.MAJORS[numerology.pair_arcana(a, b)] == "Отшельник"


def test_arcana_range():
    for y in range(1950, 2010):
        for d in (1, 9, 22, 28):
            assert 0 <= numerology.arcana_of(date(y, 12, d)) <= 21


def test_parse_date():
    assert numerology.parse_date("14.03.1996") == date(1996, 3, 14)
    assert numerology.parse_date("1/2/1990") == date(1990, 2, 1)
    assert numerology.parse_date("31.02.1990") is None
    assert numerology.parse_date("завтра") is None
    assert numerology.parse_date("01.01.2999") is None


def test_deck():
    assert len(deck.DECK) == 78 and len({c.slug for c in deck.DECK}) == 78
    cards = deck.draw(5, random.Random(1))
    assert len({c.slug for c in cards}) == 5
    assert deck.card_from_str(deck.card_to_str(cards[0])) == cards[0]
    assert deck.card_of_day(1, "2026-10-27") == deck.card_of_day(1, "2026-10-27")
    assert deck.yes_no(deck.Card("m00", "Шут", True)) == "НЕТ"
    assert deck.yes_no(deck.Card("m00", "Шут", False)) == "ДА"


def test_db_flow():
    db = DB(":memory:")
    row, created = db.ensure_user(1)
    assert created and not db.ensure_user(1)[1]
    db.set_state(1, "cmp_date", {"partner": "Аня"})
    assert db.get_state(1) == ("cmp_date", {"partner": "Аня"})
    sid = db.new_spread(1, "spread", "вопрос", ["m01", "w02r", "c03"])
    db.mark_paid(sid, "ch1", 50, 3)
    assert db.user(1)["paid_total"] == 50 and db.spread(sid)["followups_left"] == 3
    assert len(db.paid_spreads(1)) == 1
    assert db.due_followups(time.time()) == []
    assert db.due_followups(time.time() + 3.1 * 86400)[0][1] == 3
    db.update_spread(sid, asked3=1)
    assert db.due_followups(time.time() + 7.1 * 86400)[0][1] == 7
    code = db.new_gift(1)
    assert db.redeem_gift(code, 1) is None      # себе нельзя
    assert db.redeem_gift(code, 2) == 1
    assert db.redeem_gift(code, 3) is None      # второй раз нельзя
    db.update_user(1, name="Тест", birth="1990-01-01")
    db.forget(1)
    assert db.user(1)["name"] is None and db.paid_spreads(1) == []


def test_parse_json_block():
    assert parse_json_block('вот: {"a": 1} конец') == {"a": 1}
    assert parse_json_block("нет json") is None
