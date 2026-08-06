"""
File: app/auth/security.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Implements Argon2id passwords, server-side sessions, CSRF, and login throttling.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, status
from sqlalchemy import delete, select

from app.config import Settings
from app.core.time import as_utc, utc_now
from app.db.database import Database
from app.db.models import Session as UserSession
from app.db.models import User

COOKIE_NAME = "ga_session"
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Das Passwort muss mindestens 12 Zeichen lang sein.")
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        attempts = self._attempts[key]
        while attempts and attempts[0] < now - self.window_seconds:
            attempts.popleft()
        if len(attempts) >= self.attempts:
            raise HTTPException(status_code=429, detail="Zu viele Anmeldeversuche.")

    def fail(self, key: str) -> None:
        self._attempts[key].append(time.monotonic())

    def success(self, key: str) -> None:
        self._attempts.pop(key, None)


class AuthService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.limiter = LoginLimiter()

    def login(self, username: str, password: str, client_key: str) -> tuple[str, UserSession]:
        self.limiter.check(client_key)
        with self.database.sessions.begin() as session:
            user = session.scalar(
                select(User).where(User.username == username, User.enabled.is_(True))
            )
            if user is None or not verify_password(user.password_hash, password):
                self.limiter.fail(client_key)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Benutzername oder Passwort ist falsch.",
                )
            raw_token = secrets.token_urlsafe(48)
            user_session = UserSession(
                user_id=user.id,
                token_hash=token_hash(raw_token),
                csrf_token=secrets.token_urlsafe(32),
                expires_at=utc_now() + timedelta(hours=self.settings.session_hours),
            )
            session.add(user_session)
        self.limiter.success(client_key)
        return raw_token, user_session

    def authenticate(self, request: Request) -> tuple[User, UserSession]:
        raw_token = request.cookies.get(COOKIE_NAME)
        if not raw_token:
            raise HTTPException(status_code=401, detail="Anmeldung erforderlich.")
        return self.authenticate_token(raw_token)

    def authenticate_token(self, raw_token: str) -> tuple[User, UserSession]:
        with self.database.sessions.begin() as session:
            user_session = session.scalar(
                select(UserSession).where(UserSession.token_hash == token_hash(raw_token))
            )
            if user_session is None or as_utc(user_session.expires_at) <= utc_now():
                if user_session is not None:
                    session.delete(user_session)
                raise HTTPException(status_code=401, detail="Sitzung abgelaufen.")
            user = session.get(User, user_session.user_id)
            if user is None or not user.enabled:
                raise HTTPException(status_code=401, detail="Benutzer ist deaktiviert.")
            user_session.last_seen_at = utc_now()
            session.expunge(user)
            session.expunge(user_session)
            return user, user_session

    def require_csrf(self, request: Request, user_session: UserSession) -> None:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not secrets.compare_digest(supplied, user_session.csrf_token):
            raise HTTPException(status_code=403, detail="Ungültiges CSRF-Token.")

    def logout(self, request: Request) -> None:
        raw_token = request.cookies.get(COOKIE_NAME)
        if raw_token:
            with self.database.sessions.begin() as session:
                session.execute(
                    delete(UserSession).where(UserSession.token_hash == token_hash(raw_token))
                )
