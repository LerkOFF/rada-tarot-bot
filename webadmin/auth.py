"""Логины админки: пароли в scrypt, сессии в БД, защита от перебора."""
import hashlib
import hmac
import secrets
import time

SESSION_DAYS = 30
FAIL_WINDOW = 15 * 60
FAIL_LIMIT = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(got.hex(), digest)


def new_password() -> str:
    return secrets.token_urlsafe(12)


def set_user(db, login: str, password: str):
    db.con.execute(
        "INSERT INTO admin_users(login, pw_hash, created) VALUES(?,?,?) "
        "ON CONFLICT(login) DO UPDATE SET pw_hash=excluded.pw_hash",
        (login, hash_password(password), time.time()),
    )
    db.con.execute("DELETE FROM admin_sessions WHERE login=?", (login,))
    db.con.commit()


def rename_user(db, old: str, new: str):
    """Новое имя с прежним паролем. Журнал правок тоже переписываем на новое имя."""
    if not db.con.execute("SELECT 1 FROM admin_users WHERE login=?", (old,)).fetchone():
        raise SystemExit(f"нет логина {old}")
    if db.con.execute("SELECT 1 FROM admin_users WHERE login=? COLLATE NOCASE AND login!=?", (new, old)).fetchone():
        raise SystemExit(f"логин {new} уже занят")
    db.con.execute("UPDATE admin_users SET login=? WHERE login=?", (new, old))
    db.con.execute("UPDATE audit SET login=? WHERE login=?", (new, old))
    db.con.execute("UPDATE content SET updated_by=? WHERE updated_by=?", (new, old))
    db.con.execute("DELETE FROM admin_sessions WHERE login=?", (old,))
    db.con.commit()


def delete_user(db, login: str):
    db.con.execute("DELETE FROM admin_users WHERE login=?", (login,))
    db.con.execute("DELETE FROM admin_sessions WHERE login=?", (login,))
    db.con.commit()


def users(db) -> list:
    return [r["login"] for r in db.con.execute("SELECT login FROM admin_users ORDER BY login")]


def too_many_fails(db, ip: str) -> bool:
    since = time.time() - FAIL_WINDOW
    db.con.execute("DELETE FROM login_fails WHERE ts < ?", (since,))
    n = db.con.execute("SELECT COUNT(*) FROM login_fails WHERE ip=?", (ip,)).fetchone()[0]
    return n >= FAIL_LIMIT


def login(db, login_name: str, password: str, ip: str):
    """Токен новой сессии или None."""
    # регистр при входе не важен, но логин хранится и показывается как задан («V»)
    row = db.con.execute("SELECT * FROM admin_users WHERE login=? COLLATE NOCASE", (login_name,)).fetchone()
    if not row or not check_password(password, row["pw_hash"]):
        db.con.execute("INSERT INTO login_fails(ip, ts) VALUES(?,?)", (ip, time.time()))
        db.con.commit()
        return None
    login_name = row["login"]
    token = secrets.token_urlsafe(32)
    now = time.time()
    db.con.execute("INSERT INTO admin_sessions(token, login, csrf, created, expires) VALUES(?,?,?,?,?)",
                   (token, login_name, secrets.token_urlsafe(24), now, now + SESSION_DAYS * 86400))
    db.con.execute("DELETE FROM admin_sessions WHERE expires < ?", (now,))
    db.con.commit()
    db.audit(login_name, "login", "", None, ip)
    return token


def session(db, token: str):
    if not token:
        return None
    row = db.con.execute("SELECT * FROM admin_sessions WHERE token=?", (token,)).fetchone()
    if not row or row["expires"] < time.time():
        return None
    if not db.con.execute("SELECT 1 FROM admin_users WHERE login=?", (row["login"],)).fetchone():
        return None
    return row


def logout(db, token: str):
    db.con.execute("DELETE FROM admin_sessions WHERE token=?", (token,))
    db.con.commit()
