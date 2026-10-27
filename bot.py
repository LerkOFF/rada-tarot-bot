"""Zarya Tarot bot: клон @radataro_bot. Запуск: .venv/bin/python bot.py"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand, BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, LabeledPrice, Message, PreCheckoutQuery, ReplyKeyboardMarkup,
)

from rada import deck, images, numerology, texts
from rada.config import Config
from rada.db import DB
from rada.llm import LLM

log = logging.getLogger("rada")
cfg = Config()
db = DB(cfg.db_path)
llm = LLM(cfg)
router = Router()
BOT_USERNAME = {"v": ""}

BTN_DAY, BTN_ASK, BTN_ARC, BTN_MORE = "🃏 Карта дня", "🔮 Спросить карты", "✨ Мой аркан", "☰ Ещё"
MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_DAY), KeyboardButton(text=BTN_ASK)],
              [KeyboardButton(text=BTN_ARC), KeyboardButton(text=BTN_MORE)]],
    resize_keyboard=True,
)
PRIVATE = F.chat.type == "private"


def ikb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(**b) for b in row] for row in rows
    ])


def btn(text, data=None, url=None):
    return {"text": text, "callback_data": data} if data else {"text": text, "url": url}


def topics_kb(extra: bool = True):
    rows = [[btn(t, f"t:{k}")] for k, (t, _) in texts.TOPICS.items()]
    rows.append([btn("✍️ Свой вопрос", "t:own"), btn("❓ Да/нет - бесплатно", "t:yesno")])
    if extra:
        rows.append([btn("📆 Мой год", "t:year"), btn("💞 Совместимость", "t:compat")])
        rows.append([btn("📖 Полный разбор судьбы", "t:full")])
    return ikb(rows)


def chunks(text: str, n: int = 3900):
    while text:
        cut = text.rfind("\n", 0, n) if len(text) > n else len(text)
        cut = cut if cut > 0 else min(n, len(text))
        yield text[:cut]
        text = text[cut:].lstrip("\n")


async def say(msg_or_chat, bot: Bot, chat_id: int, text: str, **kw):
    for part in chunks(text):
        await bot.send_message(chat_id, part, **kw)


async def send_photo_text(bot: Bot, chat_id: int, data: bytes, text: str, name="card.jpg", **kw):
    photo = BufferedInputFile(data, filename=name)
    if len(text) <= 1000:
        return await bot.send_photo(chat_id, photo, caption=text, **kw)
    await bot.send_photo(chat_id, photo)
    for part in chunks(text):
        await bot.send_message(chat_id, part, **kw)


async def intro_video(bot: Bot, chat_id: int):
    """Видео-кружок героини. Нужен file_id своего ролика в VIDEO_NOTE_FILE_ID."""
    if cfg.video_note_id:
        try:
            await bot.send_video_note(chat_id, cfg.video_note_id)
        except Exception:
            log.warning("video note failed")
    else:
        await bot.send_chat_action(chat_id, "typing")


def today() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=cfg.tz_offset_hours)).strftime("%Y-%m-%d")


def uname(row) -> str:
    return (row["name"] if row and row["name"] else "") or ""


# ---------- старт и онбординг ----------

@router.message(CommandStart(), PRIVATE)
async def on_start(m: Message, command: CommandObject, bot: Bot):
    uid = m.from_user.id
    payload = (command.args or "").strip()
    referrer = None
    if payload.startswith("ref_") and payload[4:].isdigit() and int(payload[4:]) != uid:
        referrer = int(payload[4:])
    row, created = db.ensure_user(uid, m.from_user.language_code or "", referrer)
    if created:
        db.update_user(uid, last_push=today())  # утренние карты со следующего утра
    if created and referrer and db.user(referrer):
        db.add_credit(uid)
        db.add_credit(referrer)
        await bot.send_message(referrer, texts.REF_BONUS)
    if payload.startswith("gift_"):
        donor = db.redeem_gift(payload[5:], uid)
        if donor:
            db.add_credit(uid)
            await m.answer(texts.GIFT_RECEIVED, reply_markup=MAIN_KB)
            await bot.send_message(donor, texts.GIFT_REDEEMED)
            await m.answer(texts.ASK_CARDS, reply_markup=topics_kb(extra=False))
            return
    await intro_video(bot, m.chat.id)
    if row["name"]:
        await m.answer(texts.ASK_TOPIC, reply_markup=MAIN_KB)
        await m.answer(texts.ASK_TOPIC, reply_markup=topics_kb())
        return
    db.set_state(uid, "name")
    await m.answer(texts.GREETING.format(name=cfg.persona), reply_markup=MAIN_KB)
    await m.answer("Можно познакомиться позже:", reply_markup=ikb([[btn("Пропустить", "skip")]]))


@router.callback_query(F.data == "skip")
async def on_skip(c: CallbackQuery):
    uid = c.from_user.id
    state, data = db.get_state(uid)
    await c.answer()
    if state == "arc_date":
        db.set_state(uid, "")
        await c.message.answer(texts.ASK_TOPIC, reply_markup=topics_kb())
        return
    db.set_state(uid, "")
    await c.message.answer(texts.SKIPPED, reply_markup=MAIN_KB)
    await c.message.answer(texts.ASK_TOPIC, reply_markup=topics_kb())


@router.message(Command("terms"))
async def on_terms(m: Message):
    p = cfg.prices
    await m.answer(texts.TERMS.format(
        name=cfg.persona, p3=p.spread3, p5=p.spread5, pfu=p.followups, pb3=p.bundle3,
        pgift=p.gift, pfull=p.full, pfullr=p.full_returning))


@router.message(Command("paysupport"))
async def on_paysupport(m: Message):
    admin = f"(id {cfg.admin_ids[0]})" if cfg.admin_ids else ""
    await m.answer(texts.PAYSUPPORT.format(admin=admin))


@router.message(Command("forget"), PRIVATE)
async def on_forget(m: Message):
    db.forget(m.from_user.id)
    await m.answer(texts.FORGOT)


@router.message(Command("menu"), PRIVATE)
async def on_menu(m: Message):
    await m.answer(texts.ASK_TOPIC, reply_markup=topics_kb())


@router.message(Command("card"))
async def on_card_cmd(m: Message, bot: Bot):
    await send_card_of_day(bot, m.chat.id, m.from_user.id, with_off=False)


# ---------- карта дня ----------

async def send_card_of_day(bot: Bot, chat_id: int, uid: int, with_off: bool = False):
    row, _ = db.ensure_user(uid)
    card = deck.card_of_day(uid, today())
    try:
        body = await llm.daily(uname(row), card)
    except Exception:
        await bot.send_message(chat_id, texts.LLM_FAIL)
        return
    caption = f"🃏 {card.title}\n\n{body} 🔮"
    kb = ikb([[btn("🔕 Не присылать по утрам", "more:morning_off")]]) if with_off else None
    await send_photo_text(bot, chat_id, images.day_card(card, cfg.cards_dir), caption, reply_markup=kb)


@router.message(F.text == BTN_DAY, PRIVATE)
async def on_day(m: Message, bot: Bot):
    db.set_state(m.from_user.id, "")
    await send_card_of_day(bot, m.chat.id, m.from_user.id)


# ---------- расклады ----------

def price_for(n_cards: int) -> int:
    return cfg.prices.spread3 if n_cards == 3 else cfg.prices.spread5


async def offer_spread(bot: Bot, chat_id: int, uid: int, question: str, n_cards: int = 3):
    """Раскладывает карты, показывает коллаж, предлагает оплату (или подаренный расклад)."""
    cards = deck.draw(n_cards)
    sid = db.new_spread(uid, "spread", question, [deck.card_to_str(c) for c in cards])
    await intro_video(bot, chat_id)
    await bot.send_photo(chat_id, BufferedInputFile(images.collage(cards, cfg.cards_dir), "spread.jpg"))
    price = price_for(n_cards)
    await bot.send_message(chat_id, texts.TEASER.format(
        cards=", ".join(c.title for c in cards), price=price, fu=cfg.followup_questions))
    user = db.user(uid)
    if n_cards == 3 and user["credits"] > 0:
        await bot.send_message(chat_id, texts.CREDIT_TEASER,
                               reply_markup=ikb([[btn("🎁 Открыть подарком", f"use:{sid}")]]))
    else:
        await send_invoice(bot, chat_id, f"spread:{sid}",
                           "Расклад на три карты" if n_cards == 3 else "Глубокий расклад на пять карт",
                           f"«{question}»"[:250], price)


async def send_invoice(bot: Bot, chat_id: int, payload: str, title: str, description: str, price: int):
    await bot.send_invoice(
        chat_id, title=title, description=description or title, payload=payload,
        currency="XTR", prices=[LabeledPrice(label=title, amount=price)], provider_token="",
    )


@router.message(F.text == BTN_ASK, PRIVATE)
async def on_ask(m: Message):
    db.set_state(m.from_user.id, "own_q")
    await m.answer(texts.ASK_CARDS, reply_markup=topics_kb(extra=False))


@router.callback_query(F.data.startswith("t:"))
async def on_topic(c: CallbackQuery, bot: Bot):
    uid, chat_id = c.from_user.id, c.message.chat.id
    topic = c.data[2:]
    await c.answer()
    row, _ = db.ensure_user(uid)
    if topic in texts.TOPICS:
        db.set_state(uid, "")
        await offer_spread(bot, chat_id, uid, texts.TOPICS[topic][1])
    elif topic == "own":
        db.set_state(uid, "own_q")
        await bot.send_message(chat_id, "Напиши свой вопрос одним сообщением.")
    elif topic == "yesno":
        db.set_state(uid, "yn_q")
        await bot.send_message(chat_id, texts.ASK_YESNO)
    elif topic == "year":
        await start_year(bot, chat_id, uid, row)
    elif topic == "compat":
        db.set_state(uid, "cmp_name")
        await bot.send_message(chat_id, texts.ASK_COMPAT_NAME)
    elif topic == "full":
        await start_full(bot, chat_id, uid, row)


# ---------- да / нет ----------

async def do_yesno(m: Message, bot: Bot, question: str):
    uid = m.from_user.id
    card = deck.draw(1)[0]
    answer = deck.yes_no(card)
    await intro_video(bot, m.chat.id)
    try:
        body = await llm.yesno(question, card, answer)
    except Exception:
        await m.answer(texts.LLM_FAIL)
        return
    sid = db.new_spread(uid, "yesno", question, [deck.card_to_str(card)], text=body)
    caption = f"❓ «{question}»\n\n🃏 {card.title}\n{answer}\n\n{body}"
    await send_photo_text(bot, m.chat.id, images.day_card(card, cfg.cards_dir), caption,
                          reply_markup=ikb([[btn("🔮 Узнать подробнее", f"yn_more:{sid}")]]))


@router.callback_query(F.data.startswith("yn_more:"))
async def on_yn_more(c: CallbackQuery, bot: Bot):
    await c.answer()
    row = db.spread(int(c.data.split(":")[1]))
    if row:
        await offer_spread(bot, c.message.chat.id, c.from_user.id, row["question"])


# ---------- оплата ----------

@router.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery):
    kind, _, ref = q.invoice_payload.partition(":")
    ok = kind in ("spread", "fu", "gift", "full") and (kind == "gift" or db.spread(int(ref or 0)))
    await q.answer(ok=bool(ok), error_message=None if ok else "Расклад не найден, начни заново")


@router.message(F.successful_payment)
async def on_paid(m: Message, bot: Bot):
    pay = m.successful_payment
    kind, _, ref = pay.invoice_payload.partition(":")
    uid, chat_id = m.from_user.id, m.chat.id
    try:
        if kind == "gift":
            code = db.new_gift(uid)
            link = f"https://t.me/{BOT_USERNAME['v']}?start=gift_{code}"
            db.update_user(uid, paid_total=db.user(uid)["paid_total"] + pay.total_amount)
            await m.answer(texts.GIFT_SENT.format(link=link))
        elif kind == "spread":
            sid = int(ref)
            db.mark_paid(sid, pay.telegram_payment_charge_id, pay.total_amount, cfg.followup_questions)
            await deliver_spread(bot, chat_id, uid, sid)
        elif kind == "fu":
            sid = int(ref)
            row = db.spread(sid)
            db.update_spread(sid, followups_left=row["followups_left"] + cfg.followup_questions)
            db.update_user(uid, paid_total=db.user(uid)["paid_total"] + pay.total_amount)
            db.set_state(uid, f"fu:{sid}")
            await m.answer(texts.FU_PROMPT.format(n=cfg.followup_questions))
        elif kind == "full":
            sid = int(ref)
            db.mark_paid(sid, pay.telegram_payment_charge_id, pay.total_amount, 0)
            await deliver_full(bot, chat_id, uid, sid)
    except Exception:
        log.exception("delivery failed, refunding")
        try:
            await bot.refund_star_payment(uid, pay.telegram_payment_charge_id)
        except Exception:
            log.exception("refund failed")
        await m.answer(texts.PAY_FAIL)
        for admin in cfg.admin_ids:
            await bot.send_message(admin, f"Сбой выдачи, возврат: user {uid}, payload {pay.invoice_payload}")


@router.callback_query(F.data.startswith("use:"))
async def on_use_credit(c: CallbackQuery, bot: Bot):
    uid = c.from_user.id
    sid = int(c.data.split(":")[1])
    row, user = db.spread(sid), db.user(uid)
    await c.answer()
    if not row or row["user_id"] != uid or row["paid"] or user["credits"] < 1:
        return
    db.add_credit(uid, -1)
    db.update_spread(sid, paid=1, paid_at=time.time(), followups_left=cfg.followup_questions)
    try:
        await deliver_spread(bot, c.message.chat.id, uid, sid)
    except Exception:
        db.add_credit(uid, 1)
        db.update_spread(sid, paid=0)
        await bot.send_message(c.message.chat.id, texts.LLM_FAIL)


async def deliver_spread(bot: Bot, chat_id: int, uid: int, sid: int):
    row = db.spread(sid)
    cards = [deck.card_from_str(s) for s in json.loads(row["cards"])]
    text = await llm.spread(row["question"], cards, uname(db.user(uid)))
    db.update_spread(sid, text=text)
    await say(None, bot, chat_id, text)
    buttons = [[btn(f"🔮 Глубже: пять карт · {cfg.prices.spread5} ⭐", f"deep:{sid}")],
               [btn("🗂 Мои разборы", "more:history")]]
    await bot.send_message(chat_id, texts.FU_PROMPT.format(n=row["followups_left"] or cfg.followup_questions),
                           reply_markup=ikb(buttons))
    db.set_state(uid, f"fu:{sid}")


@router.callback_query(F.data.startswith("deep:"))
async def on_deep(c: CallbackQuery, bot: Bot):
    await c.answer()
    row = db.spread(int(c.data.split(":")[1]))
    if row and row["user_id"] == c.from_user.id:
        await offer_spread(bot, c.message.chat.id, c.from_user.id, row["question"], 5)


async def handle_followup(m: Message, bot: Bot, sid: int):
    row = db.spread(sid)
    if not row or row["user_id"] != m.from_user.id or not row["paid"]:
        db.set_state(m.from_user.id, "")
        return False
    if row["followups_left"] < 1:
        await m.answer(texts.FU_EMPTY.format(n=cfg.followup_questions, price=cfg.prices.followups),
                       reply_markup=ikb([[btn(f"Ещё {cfg.followup_questions} · {cfg.prices.followups} ⭐", f"fu_buy:{sid}")]]))
        return True
    cards = [deck.card_from_str(s) for s in json.loads(row["cards"])]
    try:
        ans = await llm.followup(row["question"], cards, row["text"], m.text)
    except Exception:
        await m.answer(texts.LLM_FAIL)
        return True
    db.update_spread(sid, followups_left=row["followups_left"] - 1)
    await say(None, bot, m.chat.id, ans)
    return True


@router.callback_query(F.data.startswith("fu_buy:"))
async def on_fu_buy(c: CallbackQuery, bot: Bot):
    await c.answer()
    sid = int(c.data.split(":")[1])
    await send_invoice(bot, c.message.chat.id, f"fu:{sid}", f"{cfg.followup_questions} уточнения",
                       "Ещё уточнения по раскладу", cfg.prices.followups)


# ---------- аркан, год, совместимость ----------

async def send_arcana(bot: Bot, chat_id: int, uid: int, name: str, birth):
    n = numerology.arcana_of(birth)
    card = deck.major(n)
    await intro_video(bot, chat_id)
    try:
        data = await llm.arcana(name, n)
    except Exception:
        await bot.send_message(chat_id, texts.LLM_FAIL)
        return
    img = images.arcana_card(card, data, BOT_USERNAME["v"], cfg.cards_dir)
    await bot.send_photo(chat_id, BufferedInputFile(img, "arcana.png"))
    body = data.get("text") or ""
    share = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME['v']}&text=" + \
            texts.ARCANA_SHARE.format(bot=BOT_USERNAME["v"]).replace(" ", "%20")
    head = f"{name or 'Друг'}, твой аркан судьбы - {card.name}.\n\n" if name else ""
    await say(None, bot, chat_id, head + body)
    await bot.send_message(chat_id, texts.ASK_TOPIC,
                           reply_markup=topics_kb_with_share(share))


def topics_kb_with_share(share_url: str):
    kb = topics_kb()
    kb.inline_keyboard.append([InlineKeyboardButton(text="📤 Поделиться арканом", url=share_url)])
    return kb


@router.message(F.text == BTN_ARC, PRIVATE)
async def on_arc(m: Message, bot: Bot):
    uid = m.from_user.id
    row, _ = db.ensure_user(uid)
    if row["birth"]:
        db.set_state(uid, "")
        await send_arcana(bot, m.chat.id, uid, uname(row), datetime.strptime(row["birth"], "%Y-%m-%d").date())
        return
    if row["name"]:
        db.set_state(uid, "arc_date")
        await m.answer(texts.ASK_BIRTH.format(user=row["name"]), reply_markup=ikb([[btn("Пропустить", "skip")]]))
    else:
        db.set_state(uid, "arc_name")
        await m.answer(texts.ASK_ARC_NAME)


async def start_year(bot: Bot, chat_id: int, uid: int, row):
    if not row["birth"]:
        db.set_state(uid, "year_date")
        await bot.send_message(chat_id, texts.ASK_YEAR_BIRTH)
        return
    await send_year(bot, chat_id, uid, row, datetime.strptime(row["birth"], "%Y-%m-%d").date())


async def send_year(bot: Bot, chat_id: int, uid: int, row, birth):
    year = datetime.now().year
    n = numerology.year_card(birth, year)
    card = deck.major(n)
    name = uname(row)
    try:
        body = await llm.year(name, n, year)
    except Exception:
        await bot.send_message(chat_id, texts.LLM_FAIL)
        return
    head = texts.YEAR_HEAD.format(user=name or "Друг", year=year, card=card.name)
    await send_photo_text(bot, chat_id, images.day_card(card, cfg.cards_dir), f"{head}\n\n{body}")


async def send_compat(bot: Bot, chat_id: int, row, partner: str, b_birth):
    if not row["birth"]:
        await bot.send_message(chat_id, texts.NO_BIRTH_FIRST)
        return
    a_birth = datetime.strptime(row["birth"], "%Y-%m-%d").date()
    n = numerology.pair_arcana(a_birth, b_birth)
    card = deck.major(n)
    a_name = uname(row) or "Ты"
    try:
        body = await llm.compat(a_name, partner, n)
    except Exception:
        await bot.send_message(chat_id, texts.LLM_FAIL)
        return
    invite = f"https://t.me/{BOT_USERNAME['v']}?start=ref_{row['id']}"
    caption = (f"💞 {a_name} + {partner}\nАркан вашей пары - {card.name}\n\n{body}\n\n"
               + texts.PAIR_FOOT.format(bot=BOT_USERNAME["v"]))
    await send_photo_text(bot, chat_id, images.day_card(card, cfg.cards_dir), caption,
                          reply_markup=ikb([[btn("💞 Пригласить: расклад на двоих в подарок", url=invite)]]))


async def start_full(bot: Bot, chat_id: int, uid: int, row):
    if not row["birth"]:
        db.set_state(uid, "full_date")
        await bot.send_message(chat_id, texts.ASK_FULL_BIRTH)
        return
    await invoice_full(bot, chat_id, uid, row)


async def invoice_full(bot: Bot, chat_id: int, uid: int, row):
    price = cfg.prices.full_returning if row["paid_total"] > 0 else cfg.prices.full
    sid = db.new_spread(uid, "full", "полный разбор судьбы", [])
    await send_invoice(bot, chat_id, f"full:{sid}", "Полный разбор судьбы",
                       "Подробный разбор характера, любви, дела и ближайшего года", price)


async def deliver_full(bot: Bot, chat_id: int, uid: int, sid: int):
    row = db.user(uid)
    birth = datetime.strptime(row["birth"], "%Y-%m-%d").date()
    n = numerology.arcana_of(birth)
    card = deck.major(n)
    year = datetime.now().year
    text = await llm.full(uname(row), birth.strftime("%d.%m.%Y"), n, numerology.year_card(birth, year), year)
    db.update_spread(sid, text=text)
    url = await publish_telegraph(f"Полный разбор судьбы: {card.name}", text)
    if url:
        await bot.send_message(chat_id, f"📖 Твой разбор готов: {url}")
    else:
        await say(None, bot, chat_id, text)


async def publish_telegraph(title: str, text: str):
    if not cfg.telegraph_token:
        return None
    nodes = [{"tag": "p", "children": [p]} for p in text.split("\n") if p.strip()]
    body = {"access_token": cfg.telegraph_token, "title": title[:200], "content": json.dumps(nodes, ensure_ascii=False)}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.telegra.ph/createPage", data=body,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
        return data["result"]["url"] if data.get("ok") else None
    except Exception:
        log.exception("telegraph failed")
        return None


# ---------- «Ещё» ----------

@router.message(F.text == BTN_MORE, PRIVATE)
async def on_more(m: Message):
    db.set_state(m.from_user.id, "")
    p = cfg.prices
    row = db.user(m.from_user.id)
    morning = [btn("🔕 Не присылать по утрам", "more:morning_off")] if (not row or row["morning"]) \
        else [btn("🔔 Присылать по утрам", "more:morning_on")]
    await m.answer(
        texts.MORE.format(hour=cfg.morning_hour, p3=p.spread3, p5=p.spread5, pfull=p.full),
        reply_markup=ikb([
            [btn("❓ Да или нет", "t:yesno"), btn("🗂 Мои разборы", "more:history")],
            [btn("🎁 Пригласить друга", "more:invite"), btn(f"🎁 Подарить расклад · {p.gift} ⭐", "more:gift")],
            morning,
            [btn("➕ Добавить в чат", url=f"https://t.me/{BOT_USERNAME['v']}?startgroup=true")],
        ]))


@router.callback_query(F.data.startswith("more:"))
async def on_more_cb(c: CallbackQuery, bot: Bot):
    uid, chat_id = c.from_user.id, c.message.chat.id
    action = c.data[5:]
    await c.answer()
    if action == "morning_off":
        db.update_user(uid, morning=0)
        await bot.send_message(chat_id, "Утренние карты выключены. Вернуть можно в «☰ Ещё».")
    elif action == "morning_on":
        db.update_user(uid, morning=1)
        await bot.send_message(chat_id, f"Буду присылать карту дня в {cfg.morning_hour}:00.")
    elif action == "invite":
        link = f"https://t.me/{BOT_USERNAME['v']}?start=ref_{uid}"
        await bot.send_message(chat_id, texts.INVITE.format(link=link))
    elif action == "gift":
        await send_invoice(bot, chat_id, "gift", "Расклад в подарок",
                           "Подаришь расклад другу: он получит ссылку", cfg.prices.gift)
    elif action == "history":
        rows = db.paid_spreads(uid)
        if not rows:
            await bot.send_message(chat_id, texts.HISTORY_EMPTY)
            return
        kb = ikb([[btn(f"{'📖' if r['kind'] == 'full' else '🔮'} {(r['question'] or '')[:40]}", f"hist:{r['id']}")]
                  for r in rows])
        await bot.send_message(chat_id, "Твои разборы:", reply_markup=kb)


@router.callback_query(F.data.startswith("hist:"))
async def on_hist(c: CallbackQuery, bot: Bot):
    await c.answer()
    row = db.spread(int(c.data.split(":")[1]))
    if row and row["user_id"] == c.from_user.id:
        await say(None, bot, c.message.chat.id, f"«{row['question']}»\n\n{row['text']}")


@router.callback_query(F.data.startswith("fb:"))
async def on_feedback(c: CallbackQuery, bot: Bot):
    _, _, answer = c.data.split(":")
    await c.answer()
    await bot.send_message(c.message.chat.id, texts.FEEDBACK_THANKS.get(answer, "Спасибо."))


# ---------- свободный текст по состоянию ----------

@router.message(F.text, PRIVATE, ~F.text.startswith("/"))
async def on_text(m: Message, bot: Bot):
    uid, text = m.from_user.id, m.text.strip()
    row, _ = db.ensure_user(uid)
    state, data = db.get_state(uid)

    if state == "name":
        db.update_user(uid, name=text[:40])
        db.set_state(uid, "")
        await m.answer(texts.NAMED.format(user=text[:40]), reply_markup=MAIN_KB)
        await m.answer(texts.ASK_TOPIC, reply_markup=topics_kb())
    elif state == "arc_name":
        db.update_user(uid, name=text[:40])
        db.set_state(uid, "arc_date")
        await m.answer(texts.ASK_BIRTH.format(user=text[:40]), reply_markup=ikb([[btn("Пропустить", "skip")]]))
    elif state in ("arc_date", "year_date", "full_date"):
        birth = numerology.parse_date(text)
        if not birth:
            await m.answer(texts.BAD_DATE)
            return
        db.update_user(uid, birth=birth.isoformat())
        db.set_state(uid, "")
        row = db.user(uid)
        if state == "arc_date":
            await send_arcana(bot, m.chat.id, uid, uname(row), birth)
        elif state == "year_date":
            await send_year(bot, m.chat.id, uid, row, birth)
        else:
            await invoice_full(bot, m.chat.id, uid, row)
    elif state == "cmp_name":
        db.set_state(uid, "cmp_date", {"partner": text[:40]})
        await m.answer(texts.ASK_COMPAT_DATE.format(partner=text[:40]))
    elif state == "cmp_date":
        birth = numerology.parse_date(text)
        if not birth:
            await m.answer(texts.BAD_DATE)
            return
        db.set_state(uid, "")
        if not row["birth"]:
            await m.answer(texts.NO_BIRTH_FIRST)
            return
        await send_compat(bot, m.chat.id, row, data.get("partner", "Он"), birth)
    elif state == "yn_q":
        db.set_state(uid, "")
        await do_yesno(m, bot, text[:300])
    elif state.startswith("fu:"):
        if not await handle_followup(m, bot, int(state[3:])):
            await offer_spread(bot, m.chat.id, uid, text[:300])
    else:
        # без состояния любой текст - это вопрос для расклада
        db.set_state(uid, "")
        await offer_spread(bot, m.chat.id, uid, text[:300])


@router.message(F.text.in_({BTN_DAY, BTN_ASK, BTN_ARC, BTN_MORE}), ~PRIVATE)
async def ignore_group_buttons(m: Message):
    return


# ---------- по расписанию ----------

async def scheduler(bot: Bot):
    while True:
        try:
            now = datetime.now(timezone.utc) + timedelta(hours=cfg.tz_offset_hours)
            if now.hour >= cfg.morning_hour:
                for u in db.morning_users(now.strftime("%Y-%m-%d")):
                    db.update_user(u["id"], last_push=now.strftime("%Y-%m-%d"))
                    try:
                        await send_card_of_day(bot, u["id"], u["id"], with_off=True)
                    except Exception:
                        log.info("morning push failed for %s", u["id"])
                    await asyncio.sleep(0.1)
            for row, days in db.due_followups(time.time()):
                db.update_spread(row["id"], **{f"asked{days}": 1})
                try:
                    await bot.send_message(row["user_id"], texts.FEEDBACK_ASK.format(q=row["question"]),
                                           reply_markup=ikb([[btn("Да", f"fb:{row['id']}:y"),
                                                              btn("Частично", f"fb:{row['id']}:p"),
                                                              btn("Нет", f"fb:{row['id']}:n")]]))
                except Exception:
                    log.info("followup failed for %s", row["user_id"])
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(60)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not cfg.bot_token:
        raise SystemExit("BOT_TOKEN не задан в .env")
    bot = Bot(cfg.bot_token)
    me = await bot.get_me()
    BOT_USERNAME["v"] = me.username
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="menu", description="Темы и вопросы"),
        BotCommand(command="card", description="Карта дня"),
        BotCommand(command="terms", description="Условия"),
        BotCommand(command="paysupport", description="Поддержка по оплате"),
        BotCommand(command="forget", description="Удалить мои данные"),
    ])
    await bot.set_my_description(texts.BOT_DESCRIPTION.format(name=cfg.persona))
    await bot.set_my_short_description(texts.BOT_SHORT)
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(scheduler(bot))
    log.info("started as @%s, llm=%s", me.username, cfg.llm_provider)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "pre_checkout_query"])


if __name__ == "__main__":
    asyncio.run(main())
