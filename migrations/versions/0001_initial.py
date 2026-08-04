"""
File: migrations/versions/0001_initial.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Creates the complete initial GA-Server schema.
Changes:
- 0.1.0: Initial implementation.
"""

from collections.abc import Sequence

from alembic import op

from app.db.models import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
