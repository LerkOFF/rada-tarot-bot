"""Прогон бота через поддельный Telegram: проверяем весь поток без сети."""
import asyncio
import os
import tempfile
from datetime import datetime

os.environ["DB_PATH"] = tempfile.mktemp(suffix=".sqlite3")
os.environ["BOT_TOKEN"] = "1:test"
os.environ["LLM_PROVIDER"] = "stub"

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, SendInvoice, SendMessage, SendPhoto
from aiogram.types import Chat, Message, Update, User, CallbackQuery, PreCheckoutQuery, SuccessfulPayment

import bot as botmod


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def stream_content(self, *a, **k):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Z", username="zarya_taro_bot")
        if isinstance(method, (SendMessage, SendPhoto, SendInvoice)):
            return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=method.chat_id, type="private"))
        return True


def make():
    sess = FakeSession()
    bot = Bot("1:test", session=sess)
    botmod.BOT_USERNAME["v"] = "zarya_taro_bot"
    dp = Dispatcher()
    dp.include_router(botmod.router)
    return bot, dp, sess


UID = 555
_n = {"i": 0}


def msg(text=None, **kw):
    _n["i"] += 1
    u = User(id=UID, is_bot=False, first_name="T")
    return Message(message_id=_n["i"], date=datetime.now(), chat=Chat(id=UID, type="private"), from_user=u, text=text, **kw)


async def send(dp, bot, text):
    await dp.feed_update(bot, Update(update_id=_n["i"] + 1000, message=msg(text)))


async def press(dp, bot, data):
    u = User(id=UID, is_bot=False, first_name="T")
    cb = CallbackQuery(id="1", from_user=u, chat_instance="x", data=data, message=msg("x"))
    await dp.feed_update(bot, Update(update_id=_n["i"] + 2000, callback_query=cb))


def texts_of(sess):
    out = []
    for c in sess.calls:
        out.append(getattr(c, "text", None) or getattr(c, "caption", None) or "")
    return "\n".join(out)


def test_full_flow():
    async def run():
        bot, dp, sess = make()
        await send(dp, bot, "/start")
        assert "Я - Заря" in texts_of(sess)
        await send(dp, bot, "Аня")                                 # имя
        await send(dp, bot, botmod.BTN_DAY)                        # карта дня
        assert any(isinstance(c, SendPhoto) for c in sess.calls)
        # да/нет
        await press(dp, bot, "t:yesno")
        await send(dp, bot, "Будет ли солнце?")
        assert "ДА" in texts_of(sess) or "НЕТ" in texts_of(sess)
        sid = botmod.db.con.execute("SELECT id FROM spreads WHERE kind='yesno'").fetchone()[0]
        n = len(sess.calls)
        await press(dp, bot, f"yn_more:{sid}")                     # платный расклад: коллаж + счёт
        invoices = [c for c in sess.calls[n:] if isinstance(c, SendInvoice)]
        assert invoices and invoices[0].currency == "XTR" and invoices[0].prices[0].amount == 50
        payload = invoices[0].payload
        # оплата
        pcq = PreCheckoutQuery(id="p", from_user=User(id=UID, is_bot=False, first_name="T"), currency="XTR",
                               total_amount=50, invoice_payload=payload)
        await dp.feed_update(bot, Update(update_id=9001, pre_checkout_query=pcq))
        pay = SuccessfulPayment(currency="XTR", total_amount=50, invoice_payload=payload,
                                telegram_payment_charge_id="c1", provider_payment_charge_id="p1")
        await dp.feed_update(bot, Update(update_id=9002, message=msg(None, successful_payment=pay)))
        assert "Прошлое:" in texts_of(sess) and "Будущее:" in texts_of(sess)   # расклад собран из библиотеки
        assert botmod.db.user(UID)["paid_total"] == 50
        # уточнение
        await send(dp, bot, "А что с работой?")
        assert botmod.db.spread(int(payload.split(":")[1]))["followups_left"] == 2
        # аркан
        await send(dp, bot, botmod.BTN_ARC)
        await send(dp, bot, "01.01.1990")
        assert "Мир" in texts_of(sess)
        # год и совместимость
        await press(dp, bot, "t:year")
        assert "Повешенный" in texts_of(sess)
        await press(dp, bot, "t:compat")
        await send(dp, bot, "Боря")
        await send(dp, bot, "02.02.1991")
        assert "Отшельник" in texts_of(sess)
        # прочее
        await send(dp, bot, "/terms")
        await send(dp, bot, botmod.BTN_MORE)
        await press(dp, bot, "more:history")
        await send(dp, bot, "/forget")
        assert botmod.db.user(UID)["name"] is None

    asyncio.run(run())
