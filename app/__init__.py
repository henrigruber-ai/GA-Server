"""
File: app/__init__.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Exposes the package version from the single VERSION source.
Changes:
- 0.1.0: Initial implementation.
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _read_version() -> str:
    candidates = (
        Path(__file__).resolve().parents[1] / "VERSION",
        Path.cwd() / "VERSION",
    )
    for version_file in candidates:
        if version_file.is_file():
            return version_file.read_text(encoding="utf-8").strip()
    try:
        return version("ga-server")
    except PackageNotFoundError as error:
        raise RuntimeError("Central VERSION source is unavailable") from error


__version__ = _read_version()
