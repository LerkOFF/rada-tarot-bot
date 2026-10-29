"""Прогон бота через поддельный Telegram: проверяем весь поток без сети."""
import asyncio
import os
import tempfile
from datetime import datetime

os.environ["DB_PATH"] = tempfile.mktemp(suffix=".sqlite3")
os.environ["MEDIA_DIR"] = tempfile.mkdtemp()
os.environ["BOT_TOKEN"] = "1:test"
os.environ["LLM_PROVIDER"] = "stub"

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, CreateInvoiceLink, SendInvoice, SendMessage, SendPhoto, SendVideoNote
from aiogram.types import Chat, Message, VideoNote, Update, User, CallbackQuery, PreCheckoutQuery, SuccessfulPayment

import bot as botmod
from rada import content


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
        if isinstance(method, SendVideoNote):
            return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=method.chat_id, type="private"),
                           video_note=VideoNote(file_id="FID123", file_unique_id="u", length=640, duration=10))
        if isinstance(method, CreateInvoiceLink):
            return "https://t.me/$testlink"
        if isinstance(method, (SendMessage, SendPhoto, SendInvoice)):
            return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=method.chat_id, type="private"))
        return True


def make():
    sess = FakeSession()
    bot = Bot("1:test", session=sess)
    botmod.BOT_USERNAME["v"] = "zarya_taro_bot"
    botmod.router._parent_router = None   # роутер один на модуль, в тестах подключаем заново
    content._store["v"] = botmod.store     # другие тесты могли поставить свою базу правок
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
        await send(dp, bot, botmod.T("BTN_DAY"))                        # карта дня
        assert any(isinstance(c, SendPhoto) for c in sess.calls)
        # да/нет
        await press(dp, bot, "t:yesno")
        await send(dp, bot, "Будет ли солнце?")
        assert "ДА" in texts_of(sess) or "НЕТ" in texts_of(sess)
        sid = botmod.db.con.execute("SELECT id FROM spreads WHERE kind='yesno'").fetchone()[0]
        n = len(sess.calls)
        await press(dp, bot, f"yn_more:{sid}")                     # платный расклад: коллаж + счёт
        invoices = [c for c in sess.calls[n:] if isinstance(c, CreateInvoiceLink)]
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
        await send(dp, bot, botmod.T("BTN_ARC"))
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
        await send(dp, bot, botmod.T("BTN_MORE"))
        await press(dp, bot, "more:history")
        await send(dp, bot, "/forget")
        assert botmod.db.user(UID)["name"] is None

    asyncio.run(run())


def test_greeting_video_note_uploaded_once_then_cached():
    async def run():
        bot, dp, sess = make()
        botmod.db.con.execute("DELETE FROM kv")
        botmod.db.con.commit()
        global UID
        old = UID
        try:
            for uid in (901, 902):
                UID = uid
                await send(dp, bot, "/start")
        finally:
            UID = old
        notes = [c for c in sess.calls if isinstance(c, SendVideoNote)]
        assert len(notes) == 2
        assert not isinstance(notes[0].video_note, str)   # первый раз загрузка файла
        assert notes[1].video_note == "FID123"            # дальше file_id из кэша
    asyncio.run(run())


def test_buttons_work_when_content_cache_expires():
    """Фильтры нижних кнопок ходят в базу: не должны делать это из пула потоков (SQLite)."""
    async def run():
        bot, dp, sess = make()
        old = botmod.store.ttl
        botmod.store.ttl = 0   # каждый запрос перечитывает правки из базы
        try:
            await send(dp, bot, "/start")
            await send(dp, bot, "Аня")
            sess.calls.clear()
            await send(dp, bot, botmod.T("BTN_DAY"))
            assert any(isinstance(c, SendPhoto) for c in sess.calls)
        finally:
            botmod.store.ttl = old

    asyncio.run(run())


def test_repeated_start_sends_welcome_once():
    async def run():
        bot, dp, sess = make()
        await send(dp, bot, "/start")
        await send(dp, bot, "Аня")
        sess.calls.clear()
        await send(dp, bot, "/start")
        texts = [c.text for c in sess.calls if isinstance(c, SendMessage)]
        assert texts.count(botmod.T("ASK_TOPIC")) == 1

    asyncio.run(run())
