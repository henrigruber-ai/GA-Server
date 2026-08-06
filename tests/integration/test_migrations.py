"""
File: tests/integration/test_migrations.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Applies the complete Alembic history to a clean SQLite database.
Changes:
- 0.1.0: Initial implementation.
"""

import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

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


def test_tasmota_migration_is_idempotent_and_preserves_existing_database(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "existing.db"
    engine = create_engine(f"sqlite:///{source_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO alembic_version VALUES ('0001_initial')"))
        connection.execute(
            text(
                "CREATE TABLE devices ("
                "id VARCHAR(36) NOT NULL PRIMARY KEY, "
                "name VARCHAR(120) NOT NULL, "
                "technical_device_id VARCHAR(120) NOT NULL UNIQUE, "
                "mqtt_topic_prefix VARCHAR(255) NOT NULL UNIQUE, "
                "mqtt_client_id VARCHAR(120) NOT NULL UNIQUE, "
                "enabled BOOLEAN NOT NULL, "
                "sort_order INTEGER NOT NULL, "
                "color VARCHAR(7) NOT NULL, "
                "is_online BOOLEAN NOT NULL, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO devices "
                "(id, name, technical_device_id, mqtt_topic_prefix, mqtt_client_id, "
                "enabled, sort_order, color, is_online, created_at, updated_at) "
                "VALUES ('old', 'Bestand', 'bestand', 'ga/devices/bestand', 'bestand', "
                "1, 0, '#123456', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    copied_path = tmp_path / "existing-copy.db"
    shutil.copy2(source_path, copied_path)
    copied_configuration = Config("alembic.ini")
    copied_configuration.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{copied_path.as_posix()}",
    )
    command.upgrade(copied_configuration, "head")
    command.upgrade(copied_configuration, "head")

    copied_engine = create_engine(f"sqlite:///{copied_path.as_posix()}")
    columns = {column["name"] for column in inspect(copied_engine).get_columns("devices")}
    indexes = {index["name"] for index in inspect(copied_engine).get_indexes("devices")}
    assert {"device_type", "controllable", "relay_index"} <= columns
    assert "ix_devices_type_enabled" in indexes
    with copied_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT name, device_type, controllable, relay_index FROM devices WHERE id = 'old'"
            )
        ).one()
    assert row == ("Bestand", "shelly_pro_3em", 0, 1)
