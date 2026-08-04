"""
File: app/api/routes_auth.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Exposes login, session discovery, and logout endpoints.
Changes:
- 0.1.0: Initial implementation.
"""

from fastapi import APIRouter, Request, Response

from app.api.schemas import LoginInput
from app.auth.security import COOKIE_NAME

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response) -> dict[str, object]:
    runtime = request.app.state.runtime
    client = request.client.host if request.client else "unknown"
    raw_token, session = runtime.auth.login(payload.username, payload.password, client)
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        max_age=runtime.settings.session_hours * 3600,
        httponly=True,
        secure=runtime.settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return {"authenticated": True, "csrf_token": session.csrf_token}


@router.get("/session")
def current_session(request: Request) -> dict[str, object]:
    runtime = request.app.state.runtime
    user, session = runtime.auth.authenticate(request)
    return {"authenticated": True, "username": user.username, "csrf_token": session.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    runtime = request.app.state.runtime
    _user, session = runtime.auth.authenticate(request)
    runtime.auth.require_csrf(request, session)
    runtime.auth.logout(request)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}
