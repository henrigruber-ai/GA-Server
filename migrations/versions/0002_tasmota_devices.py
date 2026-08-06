"""
File: migrations/versions/0002_tasmota_devices.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Adds backward-compatible Tasmota device metadata to existing databases.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect, text

revision: str = "0002_tasmota_devices"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_devices_type_enabled"


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("devices")}
    if "device_type" not in columns:
        bind.execute(
            text(
                "ALTER TABLE devices ADD COLUMN device_type VARCHAR(32) "
                "NOT NULL DEFAULT 'shelly_pro_3em'"
            )
        )
    if "controllable" not in columns:
        bind.execute(
            text("ALTER TABLE devices ADD COLUMN controllable BOOLEAN NOT NULL DEFAULT 0")
        )
    if "relay_index" not in columns:
        bind.execute(text("ALTER TABLE devices ADD COLUMN relay_index INTEGER NOT NULL DEFAULT 1"))

    indexes = {index["name"] for index in inspect(bind).get_indexes("devices")}
    if INDEX_NAME not in indexes:
        bind.execute(
            text(
                f"CREATE INDEX {INDEX_NAME} "
                "ON devices (device_type, enabled)"
            )
        )


def downgrade() -> None:
    # SQLite cannot safely drop these columns without rebuilding the table. They are
    # nullable-safe defaults and older GA-Server releases ignore unknown columns.
    bind = op.get_bind()
    indexes = {index["name"] for index in inspect(bind).get_indexes("devices")}
    if INDEX_NAME in indexes:
        bind.execute(text(f"DROP INDEX {INDEX_NAME}"))
