"""FastAPI dependencies shared by both planes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import User
from ..db.session import db_session
from ..errors import ApiError
from .api_keys import resolve_api_key
from .sessions import SESSION_COOKIE, resolve_session

DbSession = Annotated[AsyncSession, Depends(db_session)]


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_settings_from_app)]


async def require_session_user(request: Request, db: DbSession) -> User:
    """Control plane auth: the `sr_session` cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    user = await resolve_session(db, token) if token else None
    if user is None:
        raise ApiError(401, "auth", "Not signed in")
    return user


SessionUser = Annotated[User, Depends(require_session_user)]


async def require_api_key_user(request: Request, db: DbSession) -> User:
    """Data plane auth: `Authorization: Bearer sr_...`."""
    header = request.headers.get("authorization", "")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise ApiError(
            401,
            "auth",
            "Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await resolve_api_key(db, credential.strip())
    if user is None:
        raise ApiError(401, "auth", "Invalid or revoked API key")
    return user


ApiKeyUser = Annotated[User, Depends(require_api_key_user)]


async def require_reader_user(request: Request, db: DbSession) -> User:
    """`GET /v1/models` and `/v1/profiles` are safe reads the web app also calls, so they
    accept either a session cookie or an API key (docs/web.md)."""
    if request.headers.get("authorization"):
        return await require_api_key_user(request, db)
    return await require_session_user(request, db)


ReaderUser = Annotated[User, Depends(require_reader_user)]


async def require_csrf_header(request: Request) -> None:
    """CSRF pairing for the cookie-authenticated control plane: SameSite=Lax plus a header
    that a cross-site form post cannot set (docs/api.md)."""
    if not request.headers.get("x-requested-with"):
        raise ApiError(403, "auth", "Missing X-Requested-With header")


CsrfGuard = Depends(require_csrf_header)
