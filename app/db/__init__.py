"""
File: app/db/__init__.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Exposes database primitives to application modules.
Changes:
- 0.1.0: Initial implementation.
"""

from app.db.database import Database
from app.db.models import Base

__all__ = ["Base", "Database"]
