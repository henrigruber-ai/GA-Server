"""
File: app/db/database.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Configures SQLAlchemy, SQLite safety pragmas, and scoped transactions.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base


class Database:
    def __init__(self, url: str) -> None:
        connect_args: dict[str, object] = {}
        engine_args: dict[str, object] = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        if url in {"sqlite://", "sqlite:///:memory:"}:
            engine_args["poolclass"] = StaticPool
        self.url = url
        self.engine: Engine = create_engine(url, connect_args=connect_args, **engine_args)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._set_sqlite_pragmas)
        self.sessions = sessionmaker(
            bind=self.engine, class_=Session, expire_on_commit=False, autoflush=False
        )

    @staticmethod
    def _set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
        cursor.close()

    def initialize(self) -> None:
        if self.url.startswith("sqlite:///") and self.url not in {"sqlite:///:memory:"}:
            path = Path(self.url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        database_session = self.sessions()
        try:
            yield database_session
        finally:
            database_session.close()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def dispose(self) -> None:
        self.engine.dispose()
