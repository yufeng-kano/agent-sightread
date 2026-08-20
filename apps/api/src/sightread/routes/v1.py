"""Data plane `/v1/*` (docs/api.md).

Thin by design: this module validates the request, puts the bytes on disk, and hands the
work to `jobs`. It never parses a document and never talks to a model itself.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.datastructures import UploadFile

from ..auth.deps import ApiKeyUser, AppSettings, DbSession, ReaderUser
from ..db.models import Job, Result, User
from ..errors import ApiError
from ..jobs import events
from ..jobs.queue import (
    count_running_jobs,
    enqueue_job,
    find_cached_job,
    normalize_pages_spec,
    parse_pages_spec,
)
from ..jobs.runner import result_payload
from ..parsing import poppler
from ..parsing.images import ACCEPTED_IMAGE_TYPES, ImageError, probe_image
from ..parsing.profiles import BBOX_FORMAT_YXYX, PRESET_PROFILES, get_profile
from ..upstream.openrouter import fetch_image_models

router = APIRouter(prefix="/v1", tags=["data"])

PDF_MEDIA_TYPE = "application/pdf"
UPLOAD_CHUNK_BYTES = 1024 * 1024
# Base64 decodes in whole 4-character groups, so the slice length must stay a multiple of 4.
BASE64_CHUNK_CHARS = 4 * 256 * 1024
RETRY_AFTER_SECONDS = 30
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


def _resolve_kind(filename: str, media_type: str) -> tuple[str, str]:
    """Decide pdf vs image from the declared type, falling back to the file extension."""
    suffix = Path(filename).suffix.lower()
    if media_type == PDF_MEDIA_TYPE or suffix == ".pdf":
        return "pdf", PDF_MEDIA_TYPE
    if media_type in ACCEPTED_IMAGE_TYPES:
        return "image", media_type
    for accepted, extension in ACCEPTED_IMAGE_TYPES.items():
        if suffix == extension:
            return "image", accepted
    raise ApiError(400, "invalid_request", "Only PDF and jpg/png/webp/heic images are accepted")


async def _resolve_target(
    user: User, model: str | None, profile_id: str | None
) -> tuple[str, str | None, int, str]:
    """Model, profile, profile version and bbox format for this job.

    A preset profile resolves its model from the live catalog. A raw model id runs the
    default prompts and is untested by us (docs/parsing.md § Profiles).
    """
    settings_row = user.settings
    if not model and not profile_id:
        profile_id = settings_row.default_profile if settings_row else None
        model = settings_row.default_model if settings_row else None
    if model and profile_id:
        raise ApiError(400, "invalid_request", "Pass either 'model' or 'profile', not both")

    if profile_id:
        profile = get_profile(profile_id)
        if profile is None:
            raise ApiError(400, "invalid_request", f"Unknown profile '{profile_id}'")
        resolved = profile.resolve_model(await fetch_image_models())
        if resolved is None:
            raise ApiError(503, "upstream", f"Profile '{profile_id}' has no available model")
        return resolved, profile.id, profile.profile_version, profile.bbox_format

    if model:
        return model, None, 0, BBOX_FORMAT_YXYX

    raise ApiError(
        400, "invalid_request", "No model configured: pass 'model' or 'profile', or set a default"
    )


async def _upload_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
        yield chunk


async def _base64_chunks(source: str) -> AsyncIterator[bytes]:
    compact = "".join(source.split())
    for start in range(0, len(compact), BASE64_CHUNK_CHARS):
        piece = compact[start : start + BASE64_CHUNK_CHARS]
        try:
            yield base64.b64decode(piece, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(400, "invalid_request", "'source' is not valid base64") from exc


async def _store_upload(
    chunks: AsyncIterator[bytes], destination: Path, max_bytes: int
) -> tuple[int, str]:
    """Stream an upload to disk, hashing as it goes; the whole file never sits in memory."""
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("wb") as handle:
            async for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise ApiError(413, "invalid_request", "The upload exceeds UPLOAD_MAX_BYTES")
                digest.update(chunk)
                handle.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest()


async def _page_count(kind: str, path: Path, upload_dir: Path, page_cap: int) -> int:
    """Page count for a stored upload, rejecting documents we cannot read or must not run."""
    if kind == "image":
        try:
            probe_image(path)
        except ImageError as exc:
            path.unlink(missing_ok=True)
            raise ApiError(400, "invalid_request", "The image could not be decoded") from exc
        return 1

    try:
        info = await poppler.pdf_info(path, cwd=upload_dir)
    except poppler.PopplerError as exc:
        path.unlink(missing_ok=True)
        raise ApiError(400, "invalid_request", "The PDF could not be read") from exc
    if info.page_count > page_cap:
        path.unlink(missing_ok=True)
        raise ApiError(400, "invalid_request", f"The PDF exceeds the {page_cap} page cap")
    return info.page_count


def _form_value(form, field: str) -> str | None:
    value = form.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _cached_response(result: Result, wants_stream: bool) -> Response:
    payload = result_payload(result)
    payload["meta"] = {**payload["meta"], "cached": True}

    async def single_event() -> AsyncIterator[str]:
        yield events.sse("done", payload)

    if wants_stream:
        return StreamingResponse(single_event(), media_type=SSE_MEDIA_TYPE)
    return JSONResponse(payload)


@router.post("/parse")
async def parse(request: Request, user: ApiKeyUser, db: DbSession, settings: AppSettings):
    """Accept a document, dedup it, and queue the parse (docs/api.md § POST /v1/parse)."""
    content_type = request.headers.get("content-type", "")
    wants_stream = SSE_MEDIA_TYPE in request.headers.get("accept", "")
    # Cheap rejection before a byte is read; the streaming copy below enforces the real
    # cap for requests that declare no length. Base64 inflates by a third, hence the slack.
    declared_length = request.headers.get("content-length", "")
    if declared_length.isdigit() and int(declared_length) > settings.upload_max_bytes * 2:
        raise ApiError(413, "invalid_request", "The upload exceeds UPLOAD_MAX_BYTES")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise ApiError(400, "invalid_request", "Multipart requests need a 'file' part")
        filename = upload.filename or "upload"
        kind, media_type = _resolve_kind(filename, upload.content_type or "")
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
        filename = body.filename
        kind, media_type = _resolve_kind(filename, body.media_type)
        model, profile_id, pages, force = body.model, body.profile, body.pages, body.force
        chunks = _base64_chunks(body.source)

    target_model, target_profile, profile_version, bbox_format = await _resolve_target(
        user, model, profile_id
    )
    if await count_running_jobs(db, user.id) >= settings.max_jobs_per_user:
        raise ApiError(
            429,
            "rate_limit",
            "Too many running jobs; retry when one finishes",
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )

    job_id = uuid.uuid4()
    stored = upload_dir / f"{job_id}{Path(filename).suffix.lower()[:16]}"
    size_bytes, sha256 = await _store_upload(chunks, stored, settings.upload_max_bytes)

    page_count = await _page_count(kind, stored, upload_dir, settings.page_cap)
    pages_spec = normalize_pages_spec(pages)
    try:
        parse_pages_spec(pages_spec, page_count)
    except ValueError as exc:
        stored.unlink(missing_ok=True)
        raise ApiError(400, "invalid_request", str(exc)) from exc

    if not force:
        cached = await find_cached_job(
            db,
            user_id=user.id,
            sha256=sha256,
            model=target_model,
            profile=target_profile,
            profile_version=profile_version,
            pages_spec=pages_spec,
        )
        result = (
            None
            if cached is None
            else (
                await db.execute(select(Result).where(Result.job_id == cached.id))
            ).scalar_one_or_none()
        )
        if cached is not None and result is not None:
            # The cache already holds this exact parse; the fresh copy is dead weight.
            stored.unlink(missing_ok=True)
            return _cached_response(result, wants_stream)

    job = await enqueue_job(
        db,
        user_id=user.id,
        kind=kind,
        filename=filename,
        media_type=media_type,
        size_bytes=size_bytes,
        sha256=sha256,
        pages_spec=pages_spec,
        model=target_model,
        profile=target_profile,
        profile_version=profile_version,
        bbox_format=bbox_format,
        page_count=page_count,
        source_path=str(stored),
    )
    await db.commit()

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
async def job_status(job_id: uuid.UUID, user: ApiKeyUser, db: DbSession):
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
async def job_result(job_id: uuid.UUID, user: ApiKeyUser, db: DbSession):
    await _owned_job(db, job_id, user)
    result = (await db.execute(select(Result).where(Result.job_id == job_id))).scalar_one_or_none()
    if result is None:
        raise ApiError(404, "invalid_request", "This job has no result yet")
    return result_payload(result)


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: uuid.UUID, request: Request, user: ApiKeyUser, db: DbSession, settings: AppSettings
):
    """Progress stream; a terminal job replays its final event at once (docs/api.md)."""
    await _owned_job(db, job_id, user)
    return StreamingResponse(
        events.stream_job_events(request.app.state.sessionmaker, settings.database_url, job_id),
        media_type=SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
