"""Data plane `/v1/*` (docs/api.md).

Thin by design: this module validates the request, puts the bytes on disk, and hands the
work to `jobs`. It never parses a document and never talks to a model itself.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.datastructures import UploadFile

from ..auth.deps import AppSettings, BearerUser, DbSession, ReaderUser
from ..db.models import Job, Result, User
from ..errors import ApiError
from ..jobs import events
from ..jobs.intake import PDF_MEDIA_TYPE, base64_chunks, cached_payload, submit_parse
from ..jobs.runner import result_payload
from ..parsing.profiles import PRESET_PROFILES
from ..upstream.openrouter import fetch_image_models

router = APIRouter(prefix="/v1", tags=["data"])

UPLOAD_CHUNK_BYTES = 1024 * 1024
SSE_MEDIA_TYPE = "text/event-stream"


class ParseJson(BaseModel):
    """JSON fallback for clients that cannot post multipart (docs/api.md § POST /v1/parse)."""

    source: str = Field(min_length=1)
    filename: str = Field(default="upload", max_length=512)
    media_type: str = Field(default=PDF_MEDIA_TYPE, max_length=128)
    model: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=64)
    pages: str | None = Field(default=None, max_length=255)
    force: bool = False


@router.get("/models")
async def list_models(user: ReaderUser):
    """Image-input models from the live OpenRouter catalog, cached in process for ~1 h.

    `recommended` marks the models the preset profiles currently resolve to.
    """
    catalog = await fetch_image_models()
    recommended = {
        model_id
        for model_id in (profile.resolve_model(catalog) for profile in PRESET_PROFILES)
        if model_id
    }
    return {
        "data": [
            {
                "id": model["id"],
                "name": model.get("name"),
                "context_length": model.get("context_length"),
                "pricing": model.get("pricing"),
                "recommended": model["id"] in recommended,
            }
            for model in catalog
        ]
    }


@router.get("/profiles")
async def list_profiles(user: ReaderUser):
    """Preset profiles with the model each currently resolves to from the live catalog."""
    catalog = await fetch_image_models()
    profiles = []
    for profile in PRESET_PROFILES:
        model_id = profile.resolve_model(catalog)
        profiles.append(
            {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description,
                "model": model_id,
                "bbox_format": profile.bbox_format,
                "profile_version": profile.profile_version,
                "available": model_id is not None,
            }
        )
    return {"data": profiles}


# --- parse ----------------------------------------------------------------------------


async def _upload_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
        yield chunk


def _form_value(form, field: str) -> str | None:
    value = form.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _cached_response(result: Result, wants_stream: bool) -> Response:
    payload = cached_payload(result)

    async def single_event() -> AsyncIterator[str]:
        yield events.sse(events.DONE, payload)

    if wants_stream:
        return StreamingResponse(single_event(), media_type=SSE_MEDIA_TYPE)
    return JSONResponse(payload)


@router.post("/parse")
async def parse(request: Request, user: BearerUser, db: DbSession, settings: AppSettings):
    """Accept a document, dedup it, and queue the parse (docs/api.md § POST /v1/parse).

    Transport only: reading the body is this route's job, the intake sequence behind it is
    `jobs.intake` — the MCP tools run the same one (docs/project-structure.md).
    """
    content_type = request.headers.get("content-type", "")
    wants_stream = SSE_MEDIA_TYPE in request.headers.get("accept", "")
    # Cheap rejection before a byte is read; the streaming copy below enforces the real
    # cap for requests that declare no length. Base64 inflates by a third, hence the slack.
    declared_length = request.headers.get("content-length", "")
    if declared_length.isdigit() and int(declared_length) > settings.upload_max_bytes * 2:
        raise ApiError(413, "invalid_request", "The upload exceeds UPLOAD_MAX_BYTES")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise ApiError(400, "invalid_request", "Multipart requests need a 'file' part")
        filename = upload.filename or "upload"
        media_type = upload.content_type or ""
        model, profile_id, pages, force = (
            _form_value(form, "model"),
            _form_value(form, "profile"),
            _form_value(form, "pages"),
            _form_value(form, "force") in ("1", "true", "yes"),
        )
        chunks = _upload_chunks(upload)
    else:
        try:
            body = ParseJson.model_validate(await request.json())
        except ValueError as exc:
            raise ApiError(
                400, "invalid_request", "Body must be multipart/form-data or JSON with 'source'"
            ) from exc
        filename, media_type = body.filename, body.media_type
        model, profile_id, pages, force = body.model, body.profile, body.pages, body.force
        chunks = base64_chunks(body.source)

    submission = await submit_parse(
        db,
        settings,
        user=user,
        chunks=chunks,
        media_type=media_type,
        filename=filename,
        model=model,
        profile_id=profile_id,
        pages=pages,
        force=force,
    )
    if submission.cached is not None:
        return _cached_response(submission.cached, wants_stream)

    job = submission.job
    if wants_stream:
        return StreamingResponse(
            events.stream_job_events(request.app.state.sessionmaker, settings.database_url, job.id),
            media_type=SSE_MEDIA_TYPE,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return JSONResponse(
        {"job_id": str(job.id), "status": job.status}, status_code=status.HTTP_202_ACCEPTED
    )


# --- job reads ------------------------------------------------------------------------


async def _owned_job(db: DbSession, job_id: uuid.UUID, user: User) -> Job:
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.user_id == user.id))
    ).scalar_one_or_none()
    if job is None:
        raise ApiError(404, "invalid_request", "No such job")
    return job


@router.get("/jobs/{job_id}")
async def job_status(job_id: uuid.UUID, user: BearerUser, db: DbSession):
    job = await _owned_job(db, job_id, user)
    return {
        "job_id": str(job.id),
        "status": job.status,
        "page_count": job.page_count,
        "pages_done": job.pages_done,
        "error": job.error,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


@router.get("/jobs/{job_id}/result")
async def job_result(job_id: uuid.UUID, user: BearerUser, db: DbSession):
    await _owned_job(db, job_id, user)
    result = (await db.execute(select(Result).where(Result.job_id == job_id))).scalar_one_or_none()
    if result is None:
        raise ApiError(404, "invalid_request", "This job has no result yet")
    return result_payload(result)


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: uuid.UUID, request: Request, user: BearerUser, db: DbSession, settings: AppSettings
):
    """Progress stream; a terminal job replays its final event at once (docs/api.md)."""
    await _owned_job(db, job_id, user)
    return StreamingResponse(
        events.stream_job_events(request.app.state.sessionmaker, settings.database_url, job_id),
        media_type=SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
