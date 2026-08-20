"""Control plane `/api/*` — session-cookie authenticated, consumed by the web app.

Mutations additionally require an `X-Requested-With` header (CSRF pairing with
SameSite=Lax), enforced by `require_csrf_header`.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from ..auth.api_keys import create_api_key
from ..auth.crypto import encrypt_openrouter_key, mask_openrouter_key
from ..auth.deps import AppSettings, CsrfGuard, DbSession, SessionUser
from ..auth.oidc import DEV_USER_EMAIL, DEV_USER_SUB, POST_LOGIN_KEY, upsert_user
from ..auth.sessions import SESSION_COOKIE, SESSION_TTL, create_session, delete_session
from ..db.models import ApiKey, Job, OpenRouterKey, Result, UsageLog, UserSettings, utcnow
from ..errors import ApiError
from ..jobs.runner import result_payload
from ..parsing.profiles import get_profile
from ..upstream.openrouter import validate_api_key

router = APIRouter(prefix="/api", tags=["control"])

# Registered by main.py only when APP_ENV=local and AUTH_DEV_MODE=true (docs/auth.md).
dev_router = APIRouter(prefix="/api", tags=["control"])


def set_session_cookie(response: Response, token: str) -> None:
    """Cookie flags are fixed by docs/auth.md: HttpOnly, Secure, SameSite=Lax.

    Secure is set unconditionally; browsers treat `http://localhost` as a secure context,
    so local development still receives the cookie.
    """
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


# --- authentication -------------------------------------------------------------------


@router.get("/auth/login")
async def login(request: Request, settings: AppSettings):
    if not settings.google_oidc_configured:
        raise ApiError(503, "internal", "Google sign-in is not configured on this deployment")
    return await request.app.state.oauth.google.authorize_redirect(
        request, f"{settings.app_url}/api/auth/callback"
    )


@router.get("/auth/callback")
async def callback(request: Request, db: DbSession, settings: AppSettings):
    try:
        token = await request.app.state.oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        raise ApiError(400, "auth", f"Google sign-in failed: {exc.error}") from exc

    claims = token.get("userinfo") or {}
    if not claims.get("sub") or not claims.get("email"):
        raise ApiError(400, "auth", "Google sign-in returned no usable identity")

    user = await upsert_user(db, claims["sub"], claims["email"], claims.get("name"))
    session_token = await create_session(db, user)
    await db.commit()

    # A connector flow parks the authorize request that sent the user here; only a path on
    # this origin is honoured, so a parked value can never become an open redirect.
    parked = request.session.pop(POST_LOGIN_KEY, "")
    destination = parked if parked.startswith("/oauth/authorize") else settings.web_url
    response = RedirectResponse(destination, status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, session_token)
    return response


@router.post("/auth/logout", dependencies=[CsrfGuard], status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: DbSession) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await delete_session(db, token)
        await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@dev_router.post("/auth/dev-login", dependencies=[CsrfGuard])
async def dev_login(db: DbSession):
    """Local-only shortcut so the stack is demoable without Google credentials."""
    user = await upsert_user(db, DEV_USER_SUB, DEV_USER_EMAIL, "Local Developer")
    session_token = await create_session(db, user)
    await db.commit()
    response = JSONResponse({"user": {"id": user.id, "email": user.email}})
    set_session_cookie(response, session_token)
    return response


# --- account --------------------------------------------------------------------------


@router.get("/me")
async def me(user: SessionUser, db: DbSession):
    settings_row = (
        await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    ).scalar_one_or_none()
    key_row = (
        await db.execute(select(OpenRouterKey).where(OpenRouterKey.user_id == user.id))
    ).scalar_one_or_none()
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at,
        },
        "settings": {
            "default_model": settings_row.default_model if settings_row else None,
            "default_profile": settings_row.default_profile if settings_row else None,
        },
        "openrouter_key": {
            "present": key_row is not None,
            "masked": key_row.masked if key_row else None,
            "updated_at": key_row.updated_at if key_row else None,
        },
    }


# --- API keys -------------------------------------------------------------------------


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


@router.get("/keys")
async def list_keys(user: SessionUser, db: DbSession):
    rows = (
        (
            await db.execute(
                select(ApiKey)
                .where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "keys": [
            {
                "id": row.id,
                "name": row.name,
                "prefix": row.prefix,
                "created_at": row.created_at,
                "last_used_at": row.last_used_at,
            }
            for row in rows
        ]
    }


@router.post("/keys", dependencies=[CsrfGuard], status_code=status.HTTP_201_CREATED)
async def create_key(body: ApiKeyCreate, user: SessionUser, db: DbSession):
    row, plaintext = await create_api_key(db, user, body.name)
    await db.commit()
    # `key` is returned exactly once and never stored in plaintext (docs/auth.md).
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.prefix,
        "created_at": row.created_at,
        "key": plaintext,
    }


@router.delete("/keys/{key_id}", dependencies=[CsrfGuard], status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: int, user: SessionUser, db: DbSession) -> Response:
    row = (
        await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise ApiError(404, "invalid_request", "No such API key")
    row.revoked_at = utcnow()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- OpenRouter key -------------------------------------------------------------------


class OpenRouterKeyPut(BaseModel):
    key: str = Field(min_length=8, max_length=512)


@router.get("/openrouter-key")
async def get_openrouter_key(user: SessionUser, db: DbSession):
    row = (
        await db.execute(select(OpenRouterKey).where(OpenRouterKey.user_id == user.id))
    ).scalar_one_or_none()
    return {
        "present": row is not None,
        "masked": row.masked if row else None,
        "updated_at": row.updated_at if row else None,
    }


@router.put("/openrouter-key", dependencies=[CsrfGuard])
async def put_openrouter_key(
    body: OpenRouterKeyPut, user: SessionUser, db: DbSession, settings: AppSettings
):
    candidate = body.key.strip()
    if not await validate_api_key(candidate):
        raise ApiError(400, "invalid_request", "OpenRouter rejected this key")

    row = (
        await db.execute(select(OpenRouterKey).where(OpenRouterKey.user_id == user.id))
    ).scalar_one_or_none()
    ciphertext = encrypt_openrouter_key(settings.secret_key, candidate)
    masked = mask_openrouter_key(candidate)
    if row is None:
        row = OpenRouterKey(user_id=user.id, ciphertext=ciphertext, masked=masked)
        db.add(row)
    else:
        row.ciphertext = ciphertext
        row.masked = masked
        row.updated_at = utcnow()
    await db.commit()
    return {"present": True, "masked": masked, "updated_at": row.updated_at}


@router.delete("/openrouter-key", dependencies=[CsrfGuard], status_code=status.HTTP_204_NO_CONTENT)
async def delete_openrouter_key(user: SessionUser, db: DbSession) -> Response:
    await db.execute(delete(OpenRouterKey).where(OpenRouterKey.user_id == user.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- settings -------------------------------------------------------------------------


class SettingsPut(BaseModel):
    default_model: str | None = Field(default=None, max_length=255)
    default_profile: str | None = Field(default=None, max_length=64)


@router.put("/settings", dependencies=[CsrfGuard])
async def put_settings(body: SettingsPut, user: SessionUser, db: DbSession):
    if body.default_profile is not None and get_profile(body.default_profile) is None:
        raise ApiError(400, "invalid_request", f"Unknown profile '{body.default_profile}'")

    row = (
        await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    ).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user.id)
        db.add(row)
    row.default_model = body.default_model
    row.default_profile = body.default_profile
    await db.commit()
    return {"default_model": row.default_model, "default_profile": row.default_profile}


# --- usage ----------------------------------------------------------------------------


@router.get("/usage")
async def usage(user: SessionUser, db: DbSession, days: int = Query(default=30, ge=1, le=365)):
    since = utcnow() - timedelta(days=days)
    day = func.date(UsageLog.created_at)  # UTC day bucket on both PostgreSQL and SQLite

    per_day = (
        await db.execute(
            select(
                day.label("day"),
                func.sum(UsageLog.prompt_tokens),
                func.sum(UsageLog.completion_tokens),
                func.sum(UsageLog.cost),
            )
            .where(UsageLog.user_id == user.id, UsageLog.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    per_model = (
        await db.execute(
            select(
                UsageLog.model,
                func.sum(UsageLog.prompt_tokens),
                func.sum(UsageLog.completion_tokens),
                func.sum(UsageLog.cost),
            )
            .where(UsageLog.user_id == user.id, UsageLog.created_at >= since)
            .group_by(UsageLog.model)
            .order_by(UsageLog.model)
        )
    ).all()

    return {
        "days": days,
        "per_day": [
            {
                "date": str(bucket)[:10],
                "prompt_tokens": int(prompt or 0),
                "completion_tokens": int(completion or 0),
                "cost": float(cost or 0),
            }
            for bucket, prompt, completion, cost in per_day
        ],
        "per_model": [
            {
                "model": model,
                "prompt_tokens": int(prompt or 0),
                "completion_tokens": int(completion or 0),
                "cost": float(cost or 0),
            }
            for model, prompt, completion, cost in per_model
        ],
    }


# --- job history ----------------------------------------------------------------------


@router.get("/jobs")
async def list_jobs(user: SessionUser, db: DbSession, limit: int = Query(default=50, ge=1, le=200)):
    rows = (
        (
            await db.execute(
                select(Job)
                .where(Job.user_id == user.id)
                .order_by(Job.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "jobs": [
            {
                "job_id": str(row.id),
                "status": row.status,
                "filename": row.filename,
                "kind": row.kind,
                "model": row.model,
                "profile": row.profile,
                "page_count": row.page_count,
                "pages_done": row.pages_done,
                "error": row.error,
                "created_at": row.created_at,
                "finished_at": row.finished_at,
            }
            for row in rows
        ]
    }


@router.get("/jobs/{job_id}/result")
async def job_result(job_id: uuid.UUID, user: SessionUser, db: DbSession):
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.user_id == user.id))
    ).scalar_one_or_none()
    if job is None:
        raise ApiError(404, "invalid_request", "No such job")
    result = (await db.execute(select(Result).where(Result.job_id == job_id))).scalar_one_or_none()
    if result is None:
        raise ApiError(404, "invalid_request", "This job has no result yet")
    return result_payload(result)
