"""
File: tests/conftest.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Provides isolated SQLite application and authenticated client fixtures.
Changes:
- 0.1.0: Initial implementation.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.config import Settings
from app.db.models import User
from app.main import create_app


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    database_path = (tmp_path / "test.db").as_posix()
    return Settings(
        database_url=f"sqlite:///{database_path}",
        mqtt_enabled=False,
        seed_example_devices=False,
        cookie_secure=False,
    )


@pytest.fixture
def client(app_settings: Settings) -> Iterator[TestClient]:
    app = create_app(app_settings)
    with TestClient(app) as test_client:
        with app.state.runtime.database.sessions.begin() as session:
            session.add(
                User(
                    username="operator",
                    password_hash=hash_password("correct-horse-battery-staple"),
                    enabled=True,
                )
            )
        yield test_client


@pytest.fixture
def authenticated(client: TestClient) -> tuple[TestClient, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return client, response.json()["csrf_token"]
