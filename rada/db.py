"""SQLite: люди, расклады, подарки. Синхронно, нагрузка маленькая."""
import json
import secrets
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, name TEXT, birth TEXT, lang TEXT,
  morning INTEGER DEFAULT 1, credits INTEGER DEFAULT 0, referrer INTEGER,
  paid_total INTEGER DEFAULT 0, state TEXT DEFAULT '', state_data TEXT DEFAULT '{}',
  last_push TEXT DEFAULT '', created REAL
);
CREATE TABLE IF NOT EXISTS spreads (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, question TEXT,
  cards TEXT, text TEXT DEFAULT '', paid INTEGER DEFAULT 0, charge_id TEXT DEFAULT '',
  followups_left INTEGER DEFAULT 0, asked3 INTEGER DEFAULT 0, asked7 INTEGER DEFAULT 0,
  created REAL, paid_at REAL
);
CREATE TABLE IF NOT EXISTS gifts (
  code TEXT PRIMARY KEY, from_user INTEGER, redeemed_by INTEGER, created REAL
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS content (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL, updated_by TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, login TEXT, action TEXT, key TEXT,
  old TEXT, new TEXT
);
CREATE TABLE IF NOT EXISTS admin_users (
  login TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, created REAL
);
CREATE TABLE IF NOT EXISTS admin_sessions (
  token TEXT PRIMARY KEY, login TEXT, csrf TEXT, created REAL, expires REAL
);
CREATE TABLE IF NOT EXISTS login_fails (ip TEXT, ts REAL);
"""


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # базу читают двое: бот и админка, поэтому WAL и ожидание блокировки
        self.con = sqlite3.connect(path, timeout=10)
        self.con.row_factory = sqlite3.Row
        if path != ":memory:":
            self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA busy_timeout=10000")
        self.con.executescript(SCHEMA)

    # правки из админки поверх текстов по умолчанию
    def content_all(self) -> dict:
        return {r["key"]: r["value"] for r in self.con.execute("SELECT key, value FROM content")}

    def content_row(self, key: str):
        return self.con.execute("SELECT * FROM content WHERE key=?", (key,)).fetchone()

    def content_set(self, key: str, value: str, login: str, action: str = "edit"):
        row = self.content_row(key)
        old = row["value"] if row else None
        if old == value:
            return
        self.con.execute(
            "INSERT INTO content(key, value, updated, updated_by) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated, "
            "updated_by=excluded.updated_by",
            (key, value, time.time(), login),
        )
        self.audit(login, action, key, old, value)

    def content_reset(self, key: str, login: str):
        row = self.content_row(key)
        if not row:
            return
        self.con.execute("DELETE FROM content WHERE key=?", (key,))
        self.audit(login, "reset", key, row["value"], None)

    def audit(self, login: str, action: str, key: str, old=None, new=None):
        self.con.execute("INSERT INTO audit(ts, login, action, key, old, new) VALUES(?,?,?,?,?,?)",
                         (time.time(), login, action, key, old, new))
        self.con.commit()

    def audit_list(self, limit: int = 200, key: str = None):
        if key:
            return self.con.execute("SELECT * FROM audit WHERE key=? ORDER BY id DESC LIMIT ?",
                                    (key, limit)).fetchall()
        return self.con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def audit_row(self, aid: int):
        return self.con.execute("SELECT * FROM audit WHERE id=?", (aid,)).fetchone()

    def stats(self) -> dict:
        one = lambda sql: self.con.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "users": one("SELECT COUNT(*) FROM users"),
            "users_week": one(f"SELECT COUNT(*) FROM users WHERE created > {time.time() - 7 * 86400}"),
            "paid": one("SELECT COUNT(*) FROM spreads WHERE paid=1"),
            "stars": one("SELECT COALESCE(SUM(paid_total), 0) FROM users"),
        }

    # мелкий кэш (file_id видео-кружков и т.п.)
    def kv_get(self, key: str):
        row = self.con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def kv_set(self, key: str, value: str):
        self.con.execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, value))
        self.con.commit()

    # люди
    def user(self, uid: int):
        return self.con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    def ensure_user(self, uid: int, lang: str = "", referrer: int = None):
        """Возвращает (строка, создан_ли_сейчас)."""
        row = self.user(uid)
        if row:
            return row, False
        self.con.execute(
            "INSERT INTO users(id, lang, referrer, created) VALUES(?,?,?,?)",
            (uid, lang, referrer, time.time()),
        )
        self.con.commit()
        return self.user(uid), True

    def update_user(self, uid: int, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE users SET {cols} WHERE id=?", (*fields.values(), uid))
        self.con.commit()

    def add_credit(self, uid: int, n: int = 1):
        self.con.execute("UPDATE users SET credits=credits+? WHERE id=?", (n, uid))
        self.con.commit()

    def set_state(self, uid: int, state: str, data: dict = None):
        self.update_user(uid, state=state, state_data=json.dumps(data or {}, ensure_ascii=False))

    def get_state(self, uid: int):
        row = self.user(uid)
        if not row:
            return "", {}
        return row["state"] or "", json.loads(row["state_data"] or "{}")

    def forget(self, uid: int):
        self.con.execute("DELETE FROM spreads WHERE user_id=?", (uid,))
        self.con.execute(
            "UPDATE users SET name=NULL, birth=NULL, state='', state_data='{}' WHERE id=?", (uid,)
        )
        self.con.commit()

    # расклады
    def new_spread(self, uid: int, kind: str, question: str, cards: list, paid: int = 0, text: str = "") -> int:
        cur = self.con.execute(
            "INSERT INTO spreads(user_id, kind, question, cards, paid, text, created) VALUES(?,?,?,?,?,?,?)",
            (uid, kind, question, json.dumps(cards), paid, text, time.time()),
        )
        self.con.commit()
        return cur.lastrowid

    def spread(self, sid: int):
        return self.con.execute("SELECT * FROM spreads WHERE id=?", (sid,)).fetchone()

    def update_spread(self, sid: int, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE spreads SET {cols} WHERE id=?", (*fields.values(), sid))
        self.con.commit()

    def mark_paid(self, sid: int, charge_id: str, amount: int, followups: int):
        row = self.spread(sid)
        self.update_spread(sid, paid=1, charge_id=charge_id, paid_at=time.time(), followups_left=followups)
        self.con.execute("UPDATE users SET paid_total=paid_total+? WHERE id=?", (amount, row["user_id"]))
        self.con.commit()

    def paid_spreads(self, uid: int, limit: int = 20):
        return self.con.execute(
            "SELECT * FROM spreads WHERE user_id=? AND paid=1 ORDER BY id DESC LIMIT ?", (uid, limit)
        ).fetchall()

    def due_followups(self, now: float):
        """Расклады, по которым пора спросить «сбылось?» через 3 и 7 дней."""
        day = 86400
        out = []
        for row in self.con.execute("SELECT * FROM spreads WHERE paid=1 AND kind='spread' AND (asked3=0 OR asked7=0)"):
            age = now - (row["paid_at"] or row["created"])
            if not row["asked3"] and age >= 3 * day:
                out.append((row, 3))
            elif row["asked3"] and not row["asked7"] and age >= 7 * day:
                out.append((row, 7))
        return out

    # подарки
    def new_gift(self, uid: int) -> str:
        code = secrets.token_urlsafe(6)
        self.con.execute("INSERT INTO gifts(code, from_user, created) VALUES(?,?,?)", (code, uid, time.time()))
        self.con.commit()
        return code

    def redeem_gift(self, code: str, uid: int):
        row = self.con.execute("SELECT * FROM gifts WHERE code=?", (code,)).fetchone()
        if not row or row["redeemed_by"] or row["from_user"] == uid:
            return None
        self.con.execute("UPDATE gifts SET redeemed_by=? WHERE code=?", (uid, code))
        self.con.commit()
        return row["from_user"]

    def morning_users(self, today: str):
        return self.con.execute(
            "SELECT * FROM users WHERE morning=1 AND last_push!=?", (today,)
        ).fetchall()
