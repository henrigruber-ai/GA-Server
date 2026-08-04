"""
File: app/cli/__main__.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Creates the first administrator without shipping default credentials.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth.security import hash_password
from app.config import settings
from app.db.database import Database
from app.db.models import User


def create_admin(username: str | None = None) -> int:
    username = username or input("Benutzername: ").strip()
    password = getpass.getpass("Passwort (mindestens 12 Zeichen): ")
    confirmation = getpass.getpass("Passwort wiederholen: ")
    if password != confirmation:
        print("Die Passwörter stimmen nicht überein.", file=sys.stderr)
        return 2
    try:
        password_hash = hash_password(password)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    database = Database(settings.database_url)
    database.initialize()
    with database.sessions.begin() as session:
        if session.scalar(select(User).where(User.username == username)):
            print("Der Benutzername existiert bereits.", file=sys.stderr)
            return 1
        session.add(User(username=username, password_hash=password_hash, enabled=True))
    database.dispose()
    print(f"Administrator '{username}' wurde angelegt.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="GA-Server operator commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-admin", help="Create an administrator")
    create.add_argument("--username")
    arguments = parser.parse_args()
    if arguments.command == "create-admin":
        raise SystemExit(create_admin(arguments.username))


if __name__ == "__main__":
    main()
