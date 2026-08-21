"""Parse intake: everything between "bytes arrive" and "a job exists" (docs/api.md, docs/jobs.md).

`POST /v1/parse` runs this one sequence — store, hash, probe, dedup, enqueue — whichever
credential opened the door (API key, OAuth token or an upload ticket). The route keeps only
its transport concerns (multipart vs base64, SSE vs JSON); the shell owns no business logic
(docs/project-structure.md).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import upload_tickets
from ..config import Settings
from ..db.models import Job, Result, UploadTicket, User
from ..errors import ApiError
from ..parsing import poppler
from ..parsing.images import ACCEPTED_IMAGE_TYPES, ImageError, probe_image
from ..parsing.profiles import BBOX_FORMAT_YXYX, get_profile, transcription_prompt_template
from ..upstream.openrouter import fetch_image_models
from .queue import (
    count_running_jobs,
    enqueue_job,
    find_cached_job,
    normalize_pages_spec,
    parse_pages_spec,
)
from .runner import result_payload

PDF_MEDIA_TYPE = "application/pdf"
RETRY_AFTER_SECONDS = 30
# Base64 decodes in whole 4-character groups, so the slice length must stay a multiple of 4.
BASE64_CHUNK_CHARS = 4 * 256 * 1024


@dataclass
class Submission:
    """The outcome of an intake: either a queued job or a cached result, never both."""

    job: Job | None = None
    cached: Result | None = None


async def base64_chunks(source: str) -> AsyncIterator[bytes]:
    """Decode a base64 `source` in slices, so a large document never sits in memory twice."""
    compact = "".join(source.split())
    for start in range(0, len(compact), BASE64_CHUNK_CHARS):
        piece = compact[start : start + BASE64_CHUNK_CHARS]
        try:
            yield base64.b64decode(piece, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(400, "invalid_request", "'source' is not valid base64") from exc


def resolve_kind(filename: str, media_type: str) -> tuple[str, str]:
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


async def resolve_target(
    user: User, model: str | None, profile_id: str | None
) -> tuple[str, str | None, int, str, str]:
    """Model, profile, profile version, bbox format and prompt template for this job.

    A preset profile resolves its model from the live catalog. A raw model id runs the
    default prompt and is untested by us. The user's custom system prompt, when stored,
    replaces the template in every case (docs/parsing.md § Prompts).
    """
    settings_row = user.settings
    custom_prompt = settings_row.system_prompt if settings_row else None
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
        prompt = custom_prompt or profile.prompt_template
        return resolved, profile.id, profile.profile_version, profile.bbox_format, prompt

    if model:
        prompt = custom_prompt or transcription_prompt_template(None)
        return model, None, 0, BBOX_FORMAT_YXYX, prompt

    raise ApiError(
        400, "invalid_request", "No model configured: pass 'model' or 'profile', or set a default"
    )


async def store_upload(
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


async def count_pages(kind: str, path: Path, upload_dir: Path, page_cap: int) -> int:
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


async def submit_parse(
    db: AsyncSession,
    settings: Settings,
    *,
    user: User,
    chunks: AsyncIterator[bytes],
    media_type: str,
    filename: str,
    model: str | None = None,
    profile_id: str | None = None,
    pages: str | None = None,
    force: bool = False,
    ticket: UploadTicket | None = None,
) -> Submission:
    """Store the document, dedup it and queue the parse. Commits before it returns.

    An upload ticket is bound and spent by that same commit, so nothing rejected on the way
    here (413, 400, 429) costs the caller its one upload (docs/auth.md § 5).
    """
    kind, media_type = resolve_kind(filename, media_type)
    target_model, target_profile, profile_version, bbox_format, prompt = await resolve_target(
        user, model, profile_id
    )
    prompt_sha256 = hashlib.sha256(prompt.encode()).hexdigest()

    if await count_running_jobs(db, user.id) >= settings.max_jobs_per_user:
        raise ApiError(
            429,
            "rate_limit",
            "Too many running jobs; retry when one finishes",
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4()
    stored = upload_dir / f"{job_id}{Path(filename).suffix.lower()[:16]}"
    size_bytes, sha256 = await store_upload(chunks, stored, settings.upload_max_bytes)

    page_count = await count_pages(kind, stored, upload_dir, settings.page_cap)
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
            prompt_sha256=prompt_sha256,
        )
        result = (
            None
            if cached is None
            else (
                await db.execute(select(Result).where(Result.job_id == cached.id))
            ).scalar_one_or_none()
        )
        if result is not None and result.errors:
            # A degraded result (failed pages) answers its own job, never a new upload —
            # a transient upstream failure must not be replayed forever (docs/jobs.md).
            result = None
        if result is not None:
            # The cache already holds this exact parse; the fresh copy is dead weight.
            stored.unlink(missing_ok=True)
            if ticket is not None:
                upload_tickets.spend(ticket, result.job_id)
                await db.commit()
            return Submission(cached=result)

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
        prompt=prompt,
        prompt_sha256=prompt_sha256,
        page_count=page_count,
        source_path=str(stored),
    )
    if ticket is not None:
        upload_tickets.spend(ticket, job.id)
    await db.commit()
    return Submission(job=job)


def cached_payload(result: Result) -> dict:
    """The result payload of a dedup hit, flagged `meta.cached` (docs/jobs.md § Dedup)."""
    payload = result_payload(result)
    payload["meta"] = {**payload["meta"], "cached": True}
    return payload
