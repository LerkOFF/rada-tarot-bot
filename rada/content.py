"""Правки из веб-админки поверх текстов по умолчанию.

Значения по умолчанию живут в texts.py, data/library и .env. Правки лежат в таблице content,
бот перечитывает их раз в несколько секунд, поэтому перезапуск не нужен.
"""
import string
import time

from . import texts

GROUPS = [
    ("start", "Знакомство"),
    ("menu", "Главное меню и темы"),
    ("day", "Карта дня"),
    ("yesno", "Да или нет"),
    ("spread", "Расклады и оплата"),
    ("numerology", "Аркан, год, совместимость"),
    ("full", "Полный разбор"),
    ("more", "«Ещё», подарки, друзья"),
    ("feedback", "Вопрос «сбылось?»"),
    ("service", "Условия и служебное"),
    ("profile", "Профиль бота"),
]

# (ключ, раздел, что это)
ITEMS = [
    ("GREETING", "start", "Приветствие при первом /start"),
    ("SKIP_HINT", "start", "Подпись над кнопкой «Пропустить»"),
    ("BTN_SKIP", "start", "Кнопка «Пропустить»"),
    ("SKIPPED", "start", "Ответ, если знакомство пропустили"),
    ("NAMED", "start", "Ответ, когда человек назвал имя"),
    ("WELCOME_BACK", "start", "Повторный /start: подпись к нижним кнопкам"),
    ("ASK_TOPIC", "start", "Приглашение выбрать тему"),

    ("BTN_DAY", "menu", "Нижняя кнопка: карта дня"),
    ("BTN_ASK", "menu", "Нижняя кнопка: спросить карты"),
    ("BTN_ARC", "menu", "Нижняя кнопка: мой аркан"),
    ("BTN_MORE", "menu", "Нижняя кнопка: ещё"),
    ("ASK_CARDS", "menu", "Ответ на «Спросить карты»"),
    *[(f"TOPIC_{k}", "menu", f"Кнопка темы «{v[0]}»") for k, v in texts.TOPICS.items()],
    *[(f"TOPIC_{k}_Q", "menu", f"Вопрос, который задаёт тема «{v[0]}»") for k, v in texts.TOPICS.items()],
    ("BTN_OWN", "menu", "Кнопка «Свой вопрос»"),
    ("ASK_OWN", "menu", "Просьба написать свой вопрос"),
    ("BTN_YESNO_FREE", "menu", "Кнопка «Да/нет» в темах"),
    ("BTN_YEAR", "menu", "Кнопка «Мой год»"),
    ("BTN_COMPAT", "menu", "Кнопка «Совместимость»"),
    ("BTN_FULL", "menu", "Кнопка «Полный разбор»"),

    ("DAY_CAPTION", "day", "Подпись к карте дня"),
    ("BTN_MORNING_OFF", "day", "Кнопка выключить утренние карты"),
    ("BTN_MORNING_ON", "day", "Кнопка включить утренние карты"),
    ("MORNING_OFF_DONE", "day", "Ответ: утренние карты выключены"),
    ("MORNING_ON_DONE", "day", "Ответ: утренние карты включены"),

    ("ASK_YESNO", "yesno", "Просьба задать вопрос да/нет"),
    ("YESNO_CAPTION", "yesno", "Подпись к ответу да/нет"),
    ("BTN_YN_MORE", "yesno", "Кнопка «Узнать подробнее»"),

    ("TEASER", "spread", "Текст под коллажем перед оплатой"),
    ("CREDIT_TEASER", "spread", "Есть подаренный расклад"),
    ("BTN_PAY", "spread", "Кнопка оплаты под счётом, {price} - цена"),
    ("BTN_USE_GIFT", "spread", "Кнопка «Открыть подарком»"),
    ("INV_SPREAD3", "spread", "Счёт: расклад на три карты"),
    ("INV_SPREAD5", "spread", "Счёт: расклад на пять карт"),
    ("FU_PROMPT", "spread", "После расклада: можно задать уточнения"),
    ("BTN_DEEP", "spread", "Кнопка «Глубже: пять карт»"),
    ("FU_EMPTY", "spread", "Уточнения закончились"),
    ("BTN_FU_BUY", "spread", "Кнопка купить ещё уточнения"),
    ("INV_FU", "spread", "Счёт: уточнения, заголовок"),
    ("INV_FU_DESC", "spread", "Счёт: уточнения, описание"),
    ("PAY_FAIL", "spread", "Сбой после оплаты, звёзды вернули"),
    ("NOT_FOUND", "spread", "Ошибка оплаты: расклад не найден"),

    ("ASK_ARC_NAME", "numerology", "Аркан: спросить имя"),
    ("ASK_BIRTH", "numerology", "Аркан: спросить дату рождения"),
    ("BAD_DATE", "numerology", "Не разобрала дату"),
    ("ARCANA_HEAD", "numerology", "Аркан: заголовок толкования"),
    ("BTN_SHARE_ARC", "numerology", "Кнопка «Поделиться арканом»"),
    ("ARCANA_SHARE", "numerology", "Текст, с которым делятся арканом"),
    ("ASK_YEAR_BIRTH", "numerology", "Год: спросить дату рождения"),
    ("YEAR_HEAD", "numerology", "Год: заголовок"),
    ("ASK_COMPAT_NAME", "numerology", "Совместимость: спросить имя"),
    ("ASK_COMPAT_DATE", "numerology", "Совместимость: спросить дату"),
    ("NO_BIRTH_FIRST", "numerology", "Совместимость без своей даты"),
    ("PAIR_CAPTION", "numerology", "Совместимость: подпись к карте"),
    ("BTN_PAIR_INVITE", "numerology", "Кнопка «Пригласить» под совместимостью"),
    ("FRIEND", "numerology", "Как назвать человека без имени"),

    ("ASK_FULL_BIRTH", "full", "Спросить дату рождения"),
    ("INV_FULL", "full", "Счёт: заголовок"),
    ("INV_FULL_DESC", "full", "Счёт: описание"),
    ("FULL_READY", "full", "Разбор готов, ссылка"),
    ("FULL_TITLE", "full", "Заголовок статьи в Telegraph"),

    ("MORE", "more", "Текст раздела «Ещё»"),
    ("BTN_YESNO", "more", "Кнопка «Да или нет»"),
    ("BTN_HISTORY", "more", "Кнопка «Мои разборы»"),
    ("HISTORY_HEAD", "more", "Заголовок списка разборов"),
    ("HISTORY_EMPTY", "more", "Разборов пока нет"),
    ("BTN_INVITE", "more", "Кнопка «Пригласить друга»"),
    ("INVITE", "more", "Текст со ссылкой для друга"),
    ("REF_BONUS", "more", "Другу и пригласившему подарили расклад"),
    ("BTN_GIFT", "more", "Кнопка «Подарить расклад»"),
    ("INV_GIFT", "more", "Счёт: подарок, заголовок"),
    ("INV_GIFT_DESC", "more", "Счёт: подарок, описание"),
    ("GIFT_SENT", "more", "Подарок оплачен, ссылка"),
    ("GIFT_RECEIVED", "more", "Тебе подарили расклад"),
    ("GIFT_REDEEMED", "more", "Подарком воспользовались"),
    ("BTN_ADD_CHAT", "more", "Кнопка «Добавить в чат»"),

    ("FEEDBACK_ASK", "feedback", "Вопрос через 3 и 7 дней"),
    ("BTN_FB_YES", "feedback", "Кнопка «Да»"),
    ("BTN_FB_PART", "feedback", "Кнопка «Частично»"),
    ("BTN_FB_NO", "feedback", "Кнопка «Нет»"),
    ("FEEDBACK_y", "feedback", "Ответ на «Да»"),
    ("FEEDBACK_p", "feedback", "Ответ на «Частично»"),
    ("FEEDBACK_n", "feedback", "Ответ на «Нет»"),

    ("TERMS", "service", "/terms, условия"),
    ("PAYSUPPORT", "service", "/paysupport"),
    ("FORGOT", "service", "/forget, данные удалены"),
    ("LLM_FAIL", "service", "Карты молчат (сбой толкования)"),

    ("BOT_DESCRIPTION", "profile", "Описание бота (видно до /start)"),
    ("BOT_SHORT", "profile", "Короткое описание (в профиле)"),
    ("CMD_START", "profile", "Меню команд: /start"),
    ("CMD_MENU", "profile", "Меню команд: /menu"),
    ("CMD_CARD", "profile", "Меню команд: /card"),
    ("CMD_TERMS", "profile", "Меню команд: /terms"),
    ("CMD_PAYSUPPORT", "profile", "Меню команд: /paysupport"),
    ("CMD_FORGET", "profile", "Меню команд: /forget"),
]
ITEM = {k: (g, title) for k, g, title in ITEMS}

# нижняя клавиатура: бот узнаёт кнопку по тексту, поэтому надписи должны отличаться
REPLY_BUTTONS = ("BTN_DAY", "BTN_ASK", "BTN_ARC", "BTN_MORE")

LIMITS = {"BOT_DESCRIPTION": 512, "BOT_SHORT": 120, "INV_SPREAD3": 32, "INV_SPREAD5": 32, "INV_FU": 32,
          "INV_FULL": 32, "INV_GIFT": 32, "INV_FU_DESC": 255, "INV_FULL_DESC": 255, "INV_GIFT_DESC": 255}

# подстановки, доступные в любом тексте
GLOBALS = {
    "name": "имя героини",
    "bot": "ник бота без @",
    "p3": "цена расклада на 3 карты",
    "p5": "цена расклада на 5 карт",
    "pfu": "цена уточнений",
    "pb3": "цена 3 раскладов",
    "pgift": "цена подарка",
    "pfull": "цена полного разбора",
    "pfullr": "цена полного разбора для платившим",
    "hour": "час утренней карты",
    "fu": "сколько уточнений в раскладе",
}
LOCALS = {
    "user": "имя человека",
    "partner": "имя второго человека",
    "card": "название карты",
    "text": "толкование",
    "q": "вопрос человека",
    "answer": "ДА или НЕТ",
    "cards": "список выпавших карт",
    "price": "цена этого счёта",
    "n": "число уточнений",
    "link": "ссылка",
    "url": "ссылка на статью",
    "year": "год",
    "admin": "id администратора",
}

# (ключ, что это, тип, путь в Config, мин, макс)
SETTINGS = [
    ("set.persona", "Имя героини", "str", ("persona",), 1, 40),
    ("set.price.spread3", "Расклад на 3 карты, ⭐", "int", ("prices", "spread3"), 1, 10000),
    ("set.price.spread5", "Глубокий расклад на 5 карт, ⭐", "int", ("prices", "spread5"), 1, 10000),
    ("set.price.followups", "Ещё уточнения, ⭐", "int", ("prices", "followups"), 1, 10000),
    ("set.price.gift", "Расклад в подарок, ⭐", "int", ("prices", "gift"), 1, 10000),
    ("set.price.full", "Полный разбор, ⭐", "int", ("prices", "full"), 1, 10000),
    ("set.price.full_returning", "Полный разбор для платившим, ⭐", "int", ("prices", "full_returning"), 1, 10000),
    ("set.price.bundle3", "3 расклада (только в /terms), ⭐", "int", ("prices", "bundle3"), 1, 10000),
    ("set.morning_hour", "Час утренней карты (по Москве)", "int", ("morning_hour",), 0, 23),
    ("set.followups", "Уточнений в одном раскладе", "int", ("followup_questions",), 1, 10),
]
SETTING = {s[0]: s for s in SETTINGS}


def default(key: str) -> str:
    if key.startswith("TOPIC_"):
        topic = key[6:]
        if topic.endswith("_Q"):
            return texts.TOPICS[topic[:-2]][1]
        return texts.TOPICS[topic][0]
    if key.startswith("FEEDBACK_") and key != "FEEDBACK_ASK":
        return texts.FEEDBACK_THANKS[key[9:]]
    return getattr(texts, key)


def fields(text: str) -> list:
    """Имена подстановок {x} в тексте. ValueError, если скобки не закрыты."""
    out = []
    for _, name, spec, conv in string.Formatter().parse(text):
        if name is not None:
            out.append(name)
            if spec:
                out.extend(fields(spec))
    return out


def allowed(key: str) -> list:
    own = [f for f in fields(default(key)) if f not in GLOBALS]
    return own + list(GLOBALS)


def validate(key: str, value: str):
    """Текст ошибки или None."""
    if not value.strip():
        return "Пустой текст нельзя: Telegram его не отправит."
    try:
        used = fields(value)
    except ValueError:
        return "Фигурные скобки не закрыты. Чтобы написать саму скобку, удвой её: {{ или }}."
    ok = allowed(key)
    bad = [f or "{}" for f in used if f not in ok]
    if bad:
        own = [f for f in ok if f not in GLOBALS]
        hint = ", ".join("{" + f + "}" for f in own) + " и общие" if own else "только общие"
        return ("Неизвестная подстановка: " + ", ".join("{" + b.strip("{}") + "}" for b in bad)
                + f". Здесь можно {hint}: имя героини, цены, час, ник бота.")
    limit = 64 if key.startswith("BTN_") or (key.startswith("TOPIC_") and not key.endswith("_Q")) else LIMITS.get(key)
    if key.startswith("CMD_"):
        limit = 256
    if limit and len(value) > limit:
        return f"Слишком длинно: {len(value)} знаков, Telegram разрешает до {limit}."
    if key in REPLY_BUTTONS:
        for other in REPLY_BUTTONS:
            if other != key and store() and store().raw(other) == value:
                return "Такая надпись уже у другой нижней кнопки, бот их перепутает."
    return None


def validate_setting(key: str, value: str):
    _, _, kind, _, lo, hi = SETTING[key]
    value = value.strip()
    if kind == "int":
        if not value.lstrip("-").isdigit():
            return "Нужно целое число."
        if not lo <= int(value) <= hi:
            return f"Число от {lo} до {hi}."
    elif not lo <= len(value) <= hi:
        return f"Длина от {lo} до {hi} знаков."
    return None


class Content:
    def __init__(self, db, cfg=None, ttl: float = 3.0):
        self.db, self.cfg, self.ttl = db, cfg, ttl
        self.bot_username = ""
        self._data, self._at = {}, 0.0
        # значения из .env: к ним возвращаемся, если правку настройки сбросили
        self.base = {s[0]: self._cfg_get(s[3]) for s in SETTINGS} if cfg else {}

    def _cfg_get(self, path):
        obj = self.cfg
        for p in path:
            obj = getattr(obj, p)
        return obj

    def _cfg_set(self, path, value):
        obj = self.cfg
        for p in path[:-1]:
            obj = getattr(obj, p)
        setattr(obj, path[-1], value)

    def reload(self):
        self._data = self.db.content_all()
        self._at = time.monotonic()
        if self.cfg:
            for key, _, kind, path, *_ in SETTINGS:
                raw = self._data.get(key)
                value = self.base[key]
                if raw is not None and validate_setting(key, raw) is None:
                    value = int(raw) if kind == "int" else raw.strip()
                self._cfg_set(path, value)

    def fresh(self):
        if time.monotonic() - self._at > self.ttl:
            self.reload()
        return self._data

    def raw(self, key: str) -> str:
        return self.fresh().get(key, default(key))

    def overridden(self, key: str) -> bool:
        return key in self.fresh()

    def globals(self) -> dict:
        if not self.cfg:
            return {k: "" for k in GLOBALS}
        p = self.cfg.prices
        return {"name": self.cfg.persona, "bot": self.bot_username, "p3": p.spread3, "p5": p.spread5,
                "pfu": p.followups, "pb3": p.bundle3, "pgift": p.gift, "pfull": p.full,
                "pfullr": p.full_returning, "hour": self.cfg.morning_hour, "fu": self.cfg.followup_questions}

    def t(self, key: str, **kw) -> str:
        values = {**self.globals(), **kw}
        try:
            return self.raw(key).format(**values)
        except (KeyError, ValueError, IndexError, AttributeError):
            return default(key).format(**values)

    def labels(self, key: str) -> set:
        """Текущая надпись кнопки и прежняя: у людей может висеть старая клавиатура."""
        return {self.t(key), default(key).format(**self.globals())}

    def lib(self, key: str, value):
        return self.fresh().get(key, value)


_store = {"v": None}


def init(db, cfg=None, ttl: float = 3.0) -> Content:
    _store["v"] = Content(db, cfg, ttl)
    _store["v"].reload()
    return _store["v"]


def store():
    return _store["v"]


def T(key: str, **kw) -> str:
    s = store()
    if s is None:
        return default(key).format(**{**{k: "" for k in GLOBALS}, **kw})
    return s.t(key, **kw)


def lib(key: str, value):
    s = store()
    return s.lib(key, value) if s else value
