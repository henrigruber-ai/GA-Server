"""
File: tests/integration/test_migrations.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Applies the complete Alembic history to a clean SQLite database.
Changes:
- 0.1.0: Initial implementation.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.integration


def test_alembic_upgrade_head(tmp_path: Path) -> None:
    database_path = (tmp_path / "migration.db").as_posix()
    configuration = Config("alembic.ini")
    configuration.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(configuration, "head")
    tables = set(inspect(create_engine(f"sqlite:///{database_path}")).get_table_names())
    assert {
        "alembic_version",
        "users",
        "sessions",
        "devices",
        "minute_measurements",
        "device_window_stats",
        "settings",
        "audit_log",
    } <= tables
