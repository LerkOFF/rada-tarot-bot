"""Веб-админка бота.

  .venv/bin/python admin.py serve [--host 127.0.0.1] [--port 8770]
  .venv/bin/python admin.py adduser <логин>     создать или сменить пароль, пароль печатается один раз
  .venv/bin/python admin.py deluser <логин>
  .venv/bin/python admin.py users
"""
import argparse
import logging
import os

from aiohttp import web

from rada.config import Config
from rada.db import DB
from webadmin import auth
from webadmin.app import make_app


def main():
    p = argparse.ArgumentParser(description="Веб-админка бота")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default=os.environ.get("ADMIN_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("ADMIN_PORT", "8770")))
    a = sub.add_parser("adduser")
    a.add_argument("login")
    a.add_argument("--password", help="если не задан, сгенерируется")
    d = sub.add_parser("deluser")
    d.add_argument("login")
    sub.add_parser("users")
    args = p.parse_args()

    cfg = Config()
    db = DB(cfg.db_path)
    if args.cmd == "serve":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        web.run_app(make_app(cfg, db), host=args.host, port=args.port, access_log=None)
    elif args.cmd == "adduser":
        password = args.password or auth.new_password()
        auth.set_user(db, args.login.strip().lower(), password)
        print(f"{args.login.strip().lower()}: {password}")
    elif args.cmd == "deluser":
        auth.delete_user(db, args.login.strip().lower())
        print("удалён")
    elif args.cmd == "users":
        print("\n".join(auth.users(db)) or "пусто")


if __name__ == "__main__":
    main()
