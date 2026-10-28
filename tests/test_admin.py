"""Админка и правки: вход, CSRF, сохранение текста и его проверка, откат, бот видит правку."""
import asyncio
import io
import re
import tempfile

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from rada import content, library
from rada.config import Config
from rada.db import DB
from rada.deck import major
from webadmin import auth
from webadmin.app import make_app


def setup():
    cfg = Config()
    cfg.db_path = tempfile.mktemp(suffix=".sqlite3")
    cfg.media_dir = tempfile.mkdtemp()
    cfg.bot_token = ""
    db = DB(cfg.db_path)
    auth.set_user(db, "slava", "secret-pass")
    return cfg, db


async def logged_in(client):
    r = await client.post("/login", data={"login": "slava", "password": "secret-pass"}, allow_redirects=False)
    assert r.status == 303
    page = await (await client.get("/texts?g=start")).text()
    return re.search(r'name="csrf" value="([^"]+)"', page).group(1)


def run(coro):
    return asyncio.run(coro)


def test_login_required_and_wrong_password():
    async def go():
        cfg, db = setup()
        async with TestClient(TestServer(make_app(cfg, db))) as c:
            r = await c.get("/", allow_redirects=False)
            assert r.status == 302 and r.headers["Location"] == "/login"
            r = await c.post("/login", data={"login": "slava", "password": "nope"})
            assert "Неверный логин" in await r.text()
    run(go())


def test_edit_text_validation_and_revert():
    async def go():
        cfg, db = setup()
        async with TestClient(TestServer(make_app(cfg, db))) as c:
            csrf = await logged_in(c)
            # без токена формы не принимаем
            r = await c.post("/save", data={"key": "GREETING", "value": "x"}, allow_redirects=False)
            assert r.status == 403
            # неизвестная подстановка не сохраняется
            r = await c.post("/save", data={"csrf": csrf, "key": "GREETING", "value": "Привет {foo}",
                                            "back": "/texts?g=start"}, allow_redirects=False)
            assert "err=" in r.headers["Location"] and db.content_row("GREETING") is None
            # нормальная правка
            r = await c.post("/save", data={"csrf": csrf, "key": "GREETING", "value": "Я {name}, привет!",
                                            "back": "/texts?g=start"}, allow_redirects=False)
            assert "ok=" in r.headers["Location"]
            assert content.T("GREETING") == f"Я {cfg.persona}, привет!"
            # вторая правка и откат к первой
            await c.post("/save", data={"csrf": csrf, "key": "GREETING", "value": "Второй вариант", "back": "/"})
            last = db.audit_list(1)[0]
            await c.post("/history/revert", data={"csrf": csrf, "id": str(last["id"])})
            assert db.content_row("GREETING")["value"] == "Я {name}, привет!"
            # сброс к исходному
            await c.post("/reset", data={"csrf": csrf, "key": "GREETING", "back": "/"})
            assert db.content_row("GREETING") is None
            page = await (await c.get("/history")).text()
            assert "slava" in page
    run(go())


def test_reply_buttons_must_differ_and_old_label_still_works():
    async def go():
        cfg, db = setup()
        async with TestClient(TestServer(make_app(cfg, db))) as c:
            csrf = await logged_in(c)
            await c.post("/save", data={"csrf": csrf, "key": "BTN_DAY", "value": "☰ Ещё", "back": "/"})
            assert db.content_row("BTN_DAY") is None
            await c.post("/save", data={"csrf": csrf, "key": "BTN_DAY", "value": "🌞 Карта на сегодня", "back": "/"})
            labels = content.store().labels("BTN_DAY")
            assert "🌞 Карта на сегодня" in labels and "🃏 Карта дня" in labels
    run(go())


def test_settings_and_library_overrides():
    async def go():
        cfg, db = setup()
        async with TestClient(TestServer(make_app(cfg, db))) as c:
            csrf = await logged_in(c)
            await c.post("/save", data={"csrf": csrf, "key": "set.price.spread3", "value": "77", "back": "/settings"})
            assert cfg.prices.spread3 == 77
            assert "77 ⭐" in content.T("TEASER", cards="x", price=cfg.prices.spread3)
            r = await c.post("/save", data={"csrf": csrf, "key": "set.price.spread3", "value": "0", "back": "/"},
                             allow_redirects=False)
            assert "err=" in r.headers["Location"] and cfg.prices.spread3 == 77
            await c.post("/reset", data={"csrf": csrf, "key": "set.price.spread3", "back": "/"})
            assert cfg.prices.spread3 == content.store().base["set.price.spread3"]

            await c.post("/save", data={"csrf": csrf, "key": "lib.arcana.3.power", "value": "Новая сила", "back": "/"})
            assert library.arcana(3)["power"] == "Новая сила"
            await c.post("/save", data={"csrf": csrf, "key": "lib.card.m00.up.day", "value": "Шут сегодня", "back": "/"})
            assert library.daily(major(0)) == "Шут сегодня"
            r = await c.post("/save", data={"csrf": csrf, "key": "lib.card.zz.up.day", "value": "x", "back": "/"},
                             allow_redirects=False)
            assert "err=" in r.headers["Location"]
            for path in ("/deck", "/deck/m00", "/arcana", "/arcana/3", "/settings", "/videos", "/profile", "/"):
                assert (await c.get(path)).status == 200, path
    run(go())


def test_card_image_upload():
    async def go():
        cfg, db = setup()
        async with TestClient(TestServer(make_app(cfg, db))) as c:
            csrf = await logged_in(c)
            buf = io.BytesIO()
            Image.new("RGB", (300, 520), "red").save(buf, "PNG")
            data = FormData()
            data.add_field("csrf", csrf)
            data.add_field("slug", "m01")
            data.add_field("file", buf.getvalue(), filename="x.png", content_type="image/png")
            r = await c.post("/deck/image", data=data, allow_redirects=False)
            assert "ok=" in r.headers["Location"]
            r = await c.get("/files/card/m01")
            assert r.status == 200 and r.content_type == "image/jpeg"
    run(go())


def test_bad_override_falls_back_to_default():
    cfg, db = setup()
    store = content.init(db, cfg)
    db.content_set("NAMED", "Привет {нет_такого}", "test")
    store.reload()
    assert content.T("NAMED", user="Аня") == content.default("NAMED").format(user="Аня")


def test_video_upload_converts_and_bot_sees_it():
    import shutil
    import subprocess

    import pytest
    from rada.media import Media
    if not shutil.which("ffmpeg"):
        pytest.skip("нет ffmpeg")
    src = tempfile.mktemp(suffix=".mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10", "-t", "1",
                    "-pix_fmt", "yuv420p", src], check=True)

    async def go():
        cfg, db = setup()
        async with TestClient(TestServer(make_app(cfg, db))) as c:
            csrf = await logged_in(c)
            media = Media(cfg.media_dir, cfg.cards_dir)
            before = set(media.videos("yesno"))
            data = FormData()
            data.add_field("csrf", csrf)
            data.add_field("scenario", "yesno")
            data.add_field("file", open(src, "rb").read(), filename="x.mp4", content_type="video/mp4")
            r = await c.post("/videos/upload", data=data, allow_redirects=False)
            assert "ok=" in r.headers["Location"], r.headers["Location"]
            new = list(set(media.videos("yesno")) - before)
            assert len(new) == 1
            r = await c.post("/videos/delete", data={"csrf": csrf, "name": new[0].name}, allow_redirects=False)
            assert "ok=" in r.headers["Location"] and not new[0].exists()
            r = await c.post("/videos/delete", data={"csrf": csrf, "name": "../../etc/passwd"}, allow_redirects=False)
            assert "err=" in r.headers["Location"]
    run(go())


def test_rename_keeps_password_and_login_ignores_case():
    async def go():
        cfg, db = setup()
        auth.rename_user(db, "slava", "V")
        assert auth.users(db) == ["V"]
        async with TestClient(TestServer(make_app(cfg, db))) as c:
            r = await c.post("/login", data={"login": "v", "password": "secret-pass"}, allow_redirects=False)
            assert r.status == 303
            page = await (await c.get("/")).text()
            assert '<span class="who">V</span>' in page
    run(go())
