"""Веб-админка бота: тексты и кнопки, толкования, кружки, картинки карт, профиль, цены, журнал."""
import io
import json
import logging
import re
import shutil
import tempfile
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import jinja2
from aiohttp import web
from PIL import Image, ImageOps

from rada import content, library
from rada.config import Config
from rada.content import GLOBALS, GROUPS, ITEM, ITEMS, LOCALS, SETTING, SETTINGS
from rada.db import DB
from rada.deck import BY_SLUG, DECK, MAJORS, ROMAN, major
from rada.media import SCENARIO, SCENARIOS, Media, ffmpeg, to_video_note

from . import auth

warnings.filterwarnings("ignore", category=web.NotAppKeyWarning)
log = logging.getLogger("rada.admin")
HERE = Path(__file__).resolve().parent
COOKIE = "rk_admin"
MAX_UPLOAD = 200 * 1024 ** 2
LIB_MAX = 4000
MSK = timezone(timedelta(hours=3))

LIB_KEY = re.compile(
    r"^lib\.(?:card\.(?P<slug>[mwcsp]\d\d)\.(?P<pos>up|rev)\.(?P<cf>day|yesno|core)"
    r"|arcana\.(?P<an>\d{1,2})\.(?P<af>epigraph|power|blind|decision|quote|text)"
    r"|(?P<kind>year|pair)\.(?P<n>\d{1,2})|(?P<phr>intros|outros))$"
)
CARD_FIELDS = [("day", "Карта дня"), ("yesno", "Пояснение к да/нет"), ("core", "Суть для раскладов")]
ARCANA_FIELDS = [("epigraph", "Эпиграф на картинке"), ("power", "Сила"), ("blind", "Слепая зона"),
                 ("decision", "Как принимает решения"), ("quote", "Цитата"), ("text", "Толкование аркана")]
SAMPLES = {"user": "Анна", "partner": "Максим", "card": "Звезда (прямая)", "text": "Здесь будет толкование карты.",
           "q": "Получится ли переезд этой весной?", "answer": "ДА", "price": "50",
           "cards": "Звезда (прямая), Луна (перевёрнутая), Солнце (прямая)", "n": "3",
           "link": "https://t.me/zaria_taro_bot?start=ref_1", "url": "https://telegra.ph/razbor",
           "year": str(datetime.now().year), "admin": "(id 123)"}


# ---------- что можно править ----------

def lib_default(key: str):
    m = LIB_KEY.match(key)
    if not m:
        return None
    if m["slug"]:
        e = library.defaults_card(m["slug"])
        return (e.get(m["pos"]) or {}).get(m["cf"])
    if m["an"] is not None:
        return library.defaults_arcana(int(m["an"])).get(m["af"])
    if m["kind"] == "year":
        return library.defaults_year(int(m["n"])) or None
    if m["kind"] == "pair":
        return library.defaults_pair(int(m["n"])) or None
    return "\n".join(library.INTROS if m["phr"] == "intros" else library.OUTROS)


def kind_of(key: str):
    if key in ITEM:
        return "text"
    if key in SETTING:
        return "setting"
    if lib_default(key) is not None:
        return "lib"
    return None


def validate(key: str, value: str):
    kind = kind_of(key)
    if kind == "text":
        return content.validate(key, value)
    if kind == "setting":
        return content.validate_setting(key, value)
    if kind == "lib":
        if not value.strip():
            return "Пустой текст нельзя."
        if len(value) > LIB_MAX:
            return f"Слишком длинно: {len(value)} знаков, можно до {LIB_MAX}."
        return None
    return "Неизвестный ключ."


def default_of(key: str):
    """Исходное значение ключа, чтобы журнал показывал текст, а не «(исходный)»."""
    kind = kind_of(key or "")
    if kind == "text":
        return content.default(key)
    if kind == "lib":
        return lib_default(key)
    if kind == "setting" and content.store():
        return str(content.store().base.get(key, ""))
    return None


def label(key: str) -> str:
    if key in ITEM:
        group, title = ITEM[key]
        return f"{dict(GROUPS)[group]}: {title}"
    if key in SETTING:
        return f"Настройки: {SETTING[key][1]}"
    m = LIB_KEY.match(key or "")
    if m:
        if m["slug"]:
            pos = "перевёрнутая" if m["pos"] == "rev" else "прямая"
            return f"Колода: {BY_SLUG[m['slug']].name}, {pos}, {dict(CARD_FIELDS)[m['cf']].lower()}"
        if m["an"] is not None:
            return f"Аркан {MAJORS[int(m['an'])]}: {dict(ARCANA_FIELDS)[m['af']].lower()}"
        if m["kind"]:
            return f"Аркан {MAJORS[int(m['n'])]}: {'карта года' if m['kind'] == 'year' else 'аркан пары'}"
        return "Расклады: " + ("вступления" if m["phr"] == "intros" else "напутствия")
    if key.startswith("video:"):
        return "Кружок " + key[6:]
    if key.startswith("card_image:"):
        return "Картинка карты " + BY_SLUG.get(key[11:], major(0)).name
    if key == "avatar":
        return "Аватар бота"
    if key == "profile":
        return "Профиль бота в Telegram"
    return key


ACTIONS = {"edit": "изменил", "reset": "вернул исходный", "revert": "откатил", "login": "вошёл",
           "video_upload": "загрузил", "video_delete": "удалил", "card_image": "заменил",
           "card_image_reset": "вернул исходную", "avatar": "сменил", "profile": "отправил в Telegram"}


# ---------- общее ----------

def env():
    e = jinja2.Environment(loader=jinja2.FileSystemLoader(HERE / "templates"),
                           autoescape=jinja2.select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    e.filters["msk"] = lambda ts: datetime.fromtimestamp(ts, MSK).strftime("%d.%m.%Y %H:%M") if ts else ""
    e.filters["kb"] = lambda n: f"{n / 1024 / 1024:.1f} МБ" if n > 1024 * 1024 else f"{n // 1024} КБ"
    e.globals.update(groups=GROUPS, label=label, actions=ACTIONS, roman=ROMAN, majors=MAJORS)
    return e


def render(request, name: str, **ctx) -> web.Response:
    app = request.app
    sess = request.get("sess")
    ctx.update(
        user=sess["login"] if sess else None,
        csrf=sess["csrf"] if sess else "",
        path=request.path,
        query=request.query,
        persona=app["cfg"].persona,
        msg=request.query.get("ok", ""),
        err=request.query.get("err", ""),
        bot_username=app["store"].bot_username,
    )
    html = app["jinja"].get_template(name).render(**ctx)
    return web.Response(text=html, content_type="text/html")


def safe_back(value: str, fallback: str = "/") -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def go(back: str, ok: str = "", err: str = "", anchor: str = ""):
    back = re.sub(r"[?&](ok|err|ek)=[^&#]*", "", back)
    sep = "&" if "?" in back else "?"
    if ok:
        back += f"{sep}ok={quote(ok)}"
    elif err:
        # ek: ошибка покажется прямо в поле, а не над страницей
        back += f"{sep}err={quote(err)}" + (f"&ek={quote(anchor)}" if anchor else "")
    raise web.HTTPSeeOther(back + (f"#{anchor}" if anchor else ""))


async def form(request) -> dict:
    """POST-форма с проверкой CSRF-токена сессии."""
    data = await request.post()
    if data.get("csrf") != request["sess"]["csrf"]:
        raise web.HTTPForbidden(text="Форма устарела, обнови страницу.")
    return data


def client_ip(request) -> str:
    return request.headers.get("X-Forwarded-For", request.remote or "").split(",")[0].strip()


@web.middleware
async def middleware(request, handler):
    db = request.app["db"]
    request.app["store"].reload()
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and origin != "null" and urlparse(origin).netloc != request.host:
            raise web.HTTPForbidden(text="Чужой источник запроса.")
    if not (request.path.startswith("/static/") or request.path == "/login"):
        sess = auth.session(db, request.cookies.get(COOKIE))
        if not sess:
            if request.method == "GET":
                raise web.HTTPFound("/login")
            raise web.HTTPForbidden(text="Нужно войти.")
        request["sess"] = sess
    resp = await handler(request)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if not request.path.startswith(("/static/", "/files/")):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def field(store, db, key: str) -> dict:
    """Всё, что нужно шаблону для одного редактируемого поля."""
    kind = kind_of(key)
    row = db.content_row(key)
    if kind == "text":
        dflt, value = content.default(key), store.raw(key)
        group, title = ITEM[key]
        own = [f for f in content.allowed(key) if f not in GLOBALS]
        chips = [(f, LOCALS.get(f, "")) for f in own]
        chips += [(f, d) for f, d in GLOBALS.items() if "{" + f + "}" in dflt]
        more = [(f, d) for f, d in GLOBALS.items() if (f, d) not in chips]
        limit = content.LIMITS.get(key) or (64 if key.startswith("BTN_") or
                                            (key.startswith("TOPIC_") and not key.endswith("_Q")) else None)
        short = bool(limit and limit <= 64) or key.startswith("CMD_")
    else:
        dflt = lib_default(key)
        value = row["value"] if row else dflt
        title, chips, more, limit, short = "", [], [], LIB_MAX, False
    return {"key": key, "title": title, "value": value, "default": dflt, "changed": bool(row),
            "by": row["updated_by"] if row else "", "at": row["updated"] if row else 0,
            "chips": chips, "more": more, "limit": limit, "short": short, "preview": kind == "text"}


def samples(store) -> str:
    data = json.dumps({**{k: str(v) for k, v in store.globals().items()}, **SAMPLES,
                       "bot": store.bot_username or "zaria_taro_bot"}, ensure_ascii=False)
    return data.replace("</", "<\\/")


# ---------- вход ----------

async def login_page(request):
    return render(request, "login.html")


async def login_post(request):
    db = request.app["db"]
    data = await request.post()
    ip = client_ip(request)
    if auth.too_many_fails(db, ip):
        return render(request, "login.html", error="Слишком много попыток. Подожди 15 минут.")
    token = auth.login(db, (data.get("login") or "").strip(), data.get("password") or "", ip)
    if not token:
        return render(request, "login.html", error="Неверный логин или пароль.")
    resp = web.HTTPSeeOther("/")
    resp.set_cookie(COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="Lax",
                    secure=request.headers.get("X-Forwarded-Proto") == "https")
    raise resp


async def logout_post(request):
    await form(request)
    auth.logout(request.app["db"], request.cookies.get(COOKIE))
    resp = web.HTTPSeeOther("/login")
    resp.del_cookie(COOKIE)
    raise resp


# ---------- страницы ----------

async def dashboard(request):
    db = request.app["db"]
    return render(request, "dashboard.html", stats=db.stats(), recent=db.audit_list(12),
                  changed=len(db.content_all()))


async def texts_page(request):
    store, db = request.app["store"], request.app["db"]
    q = (request.query.get("q") or "").strip().lower()
    g = request.query.get("g") or ("" if q else GROUPS[0][0])
    if q:
        keys = [k for k, _, title in ITEMS
                if q in title.lower() or q in k.lower() or q in store.raw(k).lower()]
        heading = f"Поиск: {q}"
    else:
        if g not in dict(GROUPS):
            raise web.HTTPNotFound()
        keys = [k for k, grp, _ in ITEMS if grp == g]
        heading = dict(GROUPS)[g]
    counts = {}
    for k, grp, _ in ITEMS:
        if store.overridden(k):
            counts[grp] = counts.get(grp, 0) + 1
    return render(request, "texts.html", fields=[field(store, db, k) for k in keys], heading=heading,
                  g=g, q=q, counts=counts, samples=samples(store), back=request.path_qs)


async def save(request):
    data = await form(request)
    db, store = request.app["db"], request.app["store"]
    key, value = data.get("key", ""), (data.get("value") or "").replace("\r\n", "\n")
    back = safe_back(data.get("back"))
    anchor = re.sub(r"[^\w.-]", "", key)
    if kind_of(key) != "lib" and kind_of(key) != "setting":
        value = value.rstrip()
    err = validate(key, value)
    if err:
        go(back, err=err, anchor=anchor)
    if kind_of(key) == "setting":
        value = value.strip()
    db.content_set(key, value, request["sess"]["login"])
    store.reload()
    go(back, ok="Сохранено. Бот подхватит правку за несколько секунд.", anchor=anchor)


async def reset(request):
    data = await form(request)
    key = data.get("key", "")
    back = safe_back(data.get("back"))
    if not kind_of(key):
        go(back, err="Неизвестный ключ.")
    request.app["db"].content_reset(key, request["sess"]["login"])
    go(back, ok="Вернул исходный текст.", anchor=re.sub(r"[^\w.-]", "", key))


async def settings_page(request):
    store, db = request.app["store"], request.app["db"]
    rows = []
    for key, title, kind, path, lo, hi in SETTINGS:
        row = db.content_row(key)
        rows.append({"key": key, "title": title, "kind": kind, "lo": lo, "hi": hi,
                     "value": row["value"] if row else store.base[key], "base": store.base[key],
                     "changed": bool(row), "by": row["updated_by"] if row else "",
                     "at": row["updated"] if row else 0})
    return render(request, "settings.html", rows=rows, back=request.path)


async def deck_page(request):
    media = request.app["media"]
    db = request.app["db"]
    changed = set()
    for k in db.content_all():
        m = LIB_KEY.match(k)
        if m and m["slug"]:
            changed.add(m["slug"])
    groups = [("Старшие арканы", [c for c in DECK if c.is_major])]
    for letter, title in (("w", "Жезлы"), ("c", "Кубки"), ("s", "Мечи"), ("p", "Пентакли")):
        groups.append((title, [c for c in DECK if c.slug.startswith(letter)]))
    store = request.app["store"]
    phrases = [field(store, db, "lib.intros"), field(store, db, "lib.outros")]
    return render(request, "deck.html", suits=groups, changed=changed,
                  overridden={c.slug for c in DECK if media.card_overridden(c.slug)},
                  phrases=phrases, back=request.path)


async def card_page(request):
    slug = request.match_info["slug"]
    if slug not in BY_SLUG:
        raise web.HTTPNotFound()
    store, db, media = request.app["store"], request.app["db"], request.app["media"]
    positions = []
    for pos, title in (("up", "Прямая"), ("rev", "Перевёрнутая")):
        positions.append((title, [(t, field(store, db, f"lib.card.{slug}.{pos}.{f}")) for f, t in CARD_FIELDS]))
    i = [c.slug for c in DECK].index(slug)
    return render(request, "card.html", card=BY_SLUG[slug], positions=positions,
                  own_image=media.card_overridden(slug), has_image=bool(media.card_file(slug)),
                  prev=DECK[i - 1], next=DECK[(i + 1) % len(DECK)], back=request.path, v=int(time.time()))


async def arcana_list(request):
    return render(request, "arcana_list.html", items=[major(n) for n in range(22)])


async def arcana_page(request):
    n = int(request.match_info["n"])
    if not 0 <= n <= 21:
        raise web.HTTPNotFound()
    store, db = request.app["store"], request.app["db"]
    fields = [(t, field(store, db, f"lib.arcana.{n}.{f}")) for f, t in ARCANA_FIELDS]
    fields += [("Карта года", field(store, db, f"lib.year.{n}")),
               ("Аркан пары", field(store, db, f"lib.pair.{n}"))]
    return render(request, "arcana.html", n=n, card=major(n), fields=fields, back=request.path,
                  prev=(n - 1) % 22, next=(n + 1) % 22)


# ---------- кружки ----------

async def videos_page(request):
    media = request.app["media"]
    rows = []
    for key, title in SCENARIOS:
        files = [{"name": p.name, "size": p.stat().st_size, "at": p.stat().st_mtime} for p in media.videos(key)]
        rows.append({"key": key, "title": title, "files": files})
    return render(request, "videos.html", rows=rows, ffmpeg=bool(ffmpeg()), back=request.path)


async def video_upload(request):
    data = await form(request)
    media, db = request.app["media"], request.app["db"]
    scenario = data.get("scenario", "")
    upload = data.get("file")
    if scenario not in SCENARIO or not getattr(upload, "file", None):
        go("/videos", err="Выбери файл видео.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / ("in" + (Path(upload.filename or "").suffix.lower() or ".mp4"))
        with open(src, "wb") as out:
            shutil.copyfileobj(upload.file, out)
        name = media.new_video_name(scenario)
        dst = Path(tmp) / name
        err = await to_video_note(src, dst)
        if err:
            go("/videos", err=err, anchor=scenario)
        shutil.move(dst, media.video / name)
    db.audit(request["sess"]["login"], "video_upload", f"video:{name}", None, SCENARIO[scenario])
    go("/videos", ok="Кружок загружен. Бот начнёт его показывать сразу.", anchor=scenario)


async def video_delete(request):
    data = await form(request)
    media = request.app["media"]
    p = media.video_path(data.get("name", ""))
    if not p:
        go("/videos", err="Нет такого файла.")
    trash = media.root / "trash"
    trash.mkdir(exist_ok=True)
    shutil.move(p, trash / p.name)
    request.app["db"].audit(request["sess"]["login"], "video_delete", f"video:{p.name}")
    go("/videos", ok="Кружок убран. Копия лежит в корзине на сервере.", anchor=p.name.split("_")[0].split(".")[0])


async def video_file(request):
    p = request.app["media"].video_path(request.match_info["name"])
    if not p:
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})


# ---------- картинки карт ----------

def _image_from_upload(upload, max_side: int = 1400) -> Image.Image:
    img = Image.open(upload.file)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    return img


async def card_upload(request):
    data = await form(request)
    slug = data.get("slug", "")
    upload = data.get("file")
    back = f"/deck/{slug}"
    if slug not in BY_SLUG or not getattr(upload, "file", None):
        go("/deck", err="Выбери картинку.")
    try:
        img = _image_from_upload(upload)
    except Exception:
        go(back, err="Это не картинка или формат не поддерживается (нужен JPG, PNG или WEBP).")
    media = request.app["media"]
    img.save(media.cards / f"{slug}.jpg", "JPEG", quality=90)
    request.app["thumbs"].clear()
    request.app["db"].audit(request["sess"]["login"], "card_image", f"card_image:{slug}")
    go(back, ok="Картинка заменена. Пропорции как у карты: примерно 300 на 520.")


async def card_image_reset(request):
    data = await form(request)
    slug = data.get("slug", "")
    if slug not in BY_SLUG:
        go("/deck", err="Нет такой карты.")
    (request.app["media"].cards / f"{slug}.jpg").unlink(missing_ok=True)
    request.app["thumbs"].clear()
    request.app["db"].audit(request["sess"]["login"], "card_image_reset", f"card_image:{slug}")
    go(f"/deck/{slug}", ok="Вернул исходную картинку.")


async def card_file(request):
    slug = request.match_info["slug"]
    if slug not in BY_SLUG:
        raise web.HTTPNotFound()
    w = 600 if request.query.get("w") == "600" else 180
    path = request.app["media"].card_file(slug)
    cache = request.app["thumbs"]
    key = (slug, w)
    if key not in cache:
        if path:
            img = ImageOps.fit(Image.open(path).convert("RGB"), (w, int(w * 520 / 300)))
        else:
            from rada import images
            img = images.card_image(BY_SLUG[slug], []).resize((w, int(w * 520 / 300)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82)
        cache[key] = buf.getvalue()
    return web.Response(body=cache[key], content_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"})


# ---------- профиль бота ----------

async def telegram_bot(request):
    from aiogram import Bot
    token = request.app["cfg"].bot_token
    if not token:
        return None
    return Bot(token)


async def profile_page(request):
    store, db = request.app["store"], request.app["db"]
    keys = [k for k, g, _ in ITEMS if g == "profile"]
    avatar = request.app["media"].avatar_file()
    return render(request, "profile.html", fields=[field(store, db, k) for k in keys], samples=samples(store),
                  avatar=avatar.stat().st_mtime if avatar else 0, back=request.path)


async def profile_apply(request):
    await form(request)
    bot = await telegram_bot(request)
    if not bot:
        go("/profile", err="На сервере не задан токен бота.")
    from aiogram.types import BotCommand
    from rada.content import T
    try:
        await bot.set_my_commands([BotCommand(command=c, description=T(f"CMD_{c.upper()}"))
                                   for c in ("start", "menu", "card", "terms", "paysupport", "forget")])
        await bot.set_my_description(T("BOT_DESCRIPTION"))
        await bot.set_my_short_description(T("BOT_SHORT"))
    except Exception as e:
        go("/profile", err=f"Telegram не принял: {e}")
    finally:
        await bot.session.close()
    request.app["db"].audit(request["sess"]["login"], "profile", "profile")
    go("/profile", ok="Описание и команды отправлены в Telegram. В клиентах обновится в течение пары минут.")


async def avatar_upload(request):
    data = await form(request)
    upload = data.get("file")
    if not getattr(upload, "file", None):
        go("/profile", err="Выбери картинку.")
    try:
        img = _image_from_upload(upload, 1024)
    except Exception:
        go("/profile", err="Это не картинка или формат не поддерживается.")
    side = min(img.size)
    img = ImageOps.fit(img, (side, side))
    path = request.app["media"].avatar / "current.jpg"
    img.save(path, "JPEG", quality=92)
    bot = await telegram_bot(request)
    if not bot:
        go("/profile", err="Картинка сохранена, но на сервере нет токена бота.")
    from aiogram.types import FSInputFile, InputProfilePhotoStatic
    try:
        await bot.set_my_profile_photo(photo=InputProfilePhotoStatic(photo=FSInputFile(path)))
    except Exception as e:
        go("/profile", err=f"Картинка сохранена, но Telegram не принял: {e}")
    finally:
        await bot.session.close()
    request.app["db"].audit(request["sess"]["login"], "avatar", "avatar")
    go("/profile", ok="Аватар бота сменён.")


async def avatar_file(request):
    p = request.app["media"].avatar_file()
    if not p:
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "private, max-age=60"})


# ---------- журнал ----------

async def history_page(request):
    db = request.app["db"]
    key = request.query.get("key") or None
    rows = db.audit_list(300, key)
    return render(request, "history.html", rows=rows, key=key, kind_of=kind_of, default_of=default_of)


async def revert(request):
    data = await form(request)
    db = request.app["db"]
    row = db.audit_row(int(data.get("id") or 0))
    if not row or not kind_of(row["key"] or ""):
        go("/history", err="Эту запись нельзя откатить.")
    key, login = row["key"], request["sess"]["login"]
    if row["old"] is None:
        db.content_reset(key, login)
    else:
        err = validate(key, row["old"])
        if err:
            go("/history", err=err)
        db.content_set(key, row["old"], login, "revert")
    go("/history", ok=f"Откатил: {label(key)}")


# ---------- сборка ----------

async def on_startup(app):
    cfg = app["cfg"]
    if not cfg.bot_token:
        return
    from aiogram import Bot
    bot = Bot(cfg.bot_token)
    try:
        me = await bot.get_me()
        app["store"].bot_username = me.username
    except Exception:
        log.warning("getMe failed", exc_info=True)
    finally:
        await bot.session.close()


def make_app(cfg: Config = None, db: DB = None) -> web.Application:
    cfg = cfg or Config()
    db = db or DB(cfg.db_path)
    app = web.Application(middlewares=[middleware], client_max_size=MAX_UPLOAD)
    app["cfg"], app["db"] = cfg, db
    # админка перечитывает правки на каждом запросе сама, поэтому кэш долгий
    app["store"] = content.init(db, cfg, ttl=3600)
    app["media"] = Media(cfg.media_dir, cfg.cards_dir).ensure()
    app["jinja"] = env()
    app["thumbs"] = {}
    app.on_startup.append(on_startup)
    r = app.router
    r.add_get("/login", login_page)
    r.add_post("/login", login_post)
    r.add_post("/logout", logout_post)
    r.add_get("/", dashboard)
    r.add_get("/texts", texts_page)
    r.add_post("/save", save)
    r.add_post("/reset", reset)
    r.add_get("/settings", settings_page)
    r.add_get("/deck", deck_page)
    r.add_get("/deck/{slug}", card_page)
    r.add_post("/deck/image", card_upload)
    r.add_post("/deck/image/reset", card_image_reset)
    r.add_get("/arcana", arcana_list)
    r.add_get(r"/arcana/{n:\d+}", arcana_page)
    r.add_get("/videos", videos_page)
    r.add_post("/videos/upload", video_upload)
    r.add_post("/videos/delete", video_delete)
    r.add_get("/profile", profile_page)
    r.add_post("/profile/apply", profile_apply)
    r.add_post("/profile/avatar", avatar_upload)
    r.add_get("/history", history_page)
    r.add_post("/history/revert", revert)
    r.add_get("/files/video/{name}", video_file)
    r.add_get("/files/card/{slug}", card_file)
    r.add_get("/files/avatar", avatar_file)
    r.add_static("/static/", HERE / "static")
    return app
