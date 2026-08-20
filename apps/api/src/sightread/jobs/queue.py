"""The job queue (docs/jobs.md). The only module that knows the queue is PostgreSQL.

A job row *is* its queue entry, so creating a job and enqueueing it are one transaction —
there is no broker and no dual write. Claiming is `FOR UPDATE SKIP LOCKED`, FIFO, with the
per-user cap applied at claim time so one user cannot monopolise the workers.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Job, JobPage, utcnow
from ..parsing.profiles import PIPELINE_VERSION

# PostgreSQL claim (docs/jobs.md). The correlated count applies the per-user running cap
# to the same scan that picks the oldest queued job.
CLAIM_SQL = text(
    """
    UPDATE jobs SET status = 'running', started_at = now()
    WHERE id = (
      SELECT j.id FROM jobs j
      WHERE j.status = 'queued'
        AND (
          SELECT count(*) FROM jobs running
          WHERE running.user_id = j.user_id AND running.status = 'running'
        ) < :max_jobs_per_user
      ORDER BY j.created_at
      FOR UPDATE SKIP LOCKED LIMIT 1
    )
    RETURNING id
    """
)

# SQLite has neither SKIP LOCKED nor row locks. The fallback keeps the whole test suite
# runnable with no services; the guarded UPDATE still makes a double claim impossible.
CLAIM_SQL_SQLITE_SELECT = text(
    """
    SELECT j.id FROM jobs j
    WHERE j.status = 'queued'
      AND (
        SELECT count(*) FROM jobs running
        WHERE running.user_id = j.user_id AND running.status = 'running'
      ) < :max_jobs_per_user
    ORDER BY j.created_at LIMIT 1
    """
)

_PAGES_SPEC_RE = re.compile(r"^\d+(-\d+)?(,\d+(-\d+)?)*$")


def parse_pages_spec(spec: str, page_count: int) -> list[int]:
    """Expand `"1-5,8"` into page numbers. Empty means every page.

    Raises `ValueError` for malformed input or a selection outside the document.
    """
    if not spec:
        return list(range(1, page_count + 1))
    if not _PAGES_SPEC_RE.match(spec):
        raise ValueError("pages must look like '1-5,8'")

    pages: set[int] = set()
    for part in spec.split(","):
        first, _, last = part.partition("-")
        start, end = int(first), int(last or first)
        if start < 1 or end < start or end > page_count:
            raise ValueError(f"pages selects a page outside 1-{page_count}")
        pages.update(range(start, end + 1))
    return sorted(pages)


def normalize_pages_spec(spec: str | None) -> str:
    """Canonical form stored on the job and used in the dedup key: no whitespace."""
    return re.sub(r"\s+", "", spec or "")


async def count_running_jobs(db: AsyncSession, user_id: int) -> int:
    """Running jobs for one user — the cap `POST /v1/parse` enforces (docs/jobs.md)."""
    return (
        await db.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.user_id == user_id, Job.status == "running")
        )
    ).scalar_one()


async def find_cached_job(
    db: AsyncSession,
    *,
    user_id: int,
    sha256: str,
    model: str,
    profile: str | None,
    profile_version: int,
    pages_spec: str,
) -> Job | None:
    """The dedup lookup: same user, same bytes, same model/profile/pages/pipeline."""
    return (
        await db.execute(
            select(Job)
            .where(
                Job.user_id == user_id,
                Job.sha256 == sha256,
                Job.model == model,
                Job.profile.is_(profile) if profile is None else Job.profile == profile,
                Job.profile_version == profile_version,
                Job.pages_spec == pages_spec,
                Job.pipeline_version == PIPELINE_VERSION,
                Job.status == "succeeded",
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def enqueue_job(
    db: AsyncSession,
    *,
    user_id: int,
    kind: str,
    filename: str,
    media_type: str,
    size_bytes: int,
    sha256: str,
    pages_spec: str,
    model: str,
    profile: str | None,
    profile_version: int,
    bbox_format: str,
    page_count: int,
    source_path: str,
) -> Job:
    """Create the queued job row. The caller commits — creation and enqueue are one act."""
    job = Job(
        id=uuid.uuid4(),
        user_id=user_id,
        kind=kind,
        filename=filename,
        media_type=media_type,
        size_bytes=size_bytes,
        sha256=sha256,
        pages_spec=pages_spec,
        model=model,
        profile=profile,
        profile_version=profile_version,
        pipeline_version=PIPELINE_VERSION,
        bbox_format=bbox_format,
        status="queued",
        page_count=page_count,
        pages_done=0,
        source_path=source_path,
        created_at=utcnow(),
    )
    db.add(job)
    await db.flush()
    return job


async def claim_next_job(db: AsyncSession, max_jobs_per_user: int) -> uuid.UUID | None:
    """Claim the oldest queued job whose user is under the running cap, or None."""
    if db.get_bind().dialect.name == "postgresql":
        claimed = (
            await db.execute(CLAIM_SQL, {"max_jobs_per_user": max_jobs_per_user})
        ).scalar_one_or_none()
        await db.commit()
        return claimed

    candidate = (
        await db.execute(CLAIM_SQL_SQLITE_SELECT, {"max_jobs_per_user": max_jobs_per_user})
    ).scalar_one_or_none()
    if candidate is None:
        return None
    job_id = uuid.UUID(str(candidate))
    updated = await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "queued")
        .values(status="running", started_at=utcnow())
    )
    await db.commit()
    return job_id if updated.rowcount == 1 else None


async def requeue_job(db: AsyncSession, job_id: uuid.UUID) -> None:
    """Put an interrupted job back on the queue and forget its partial progress.

    Shutdown mid-run reparses from scratch: pages are not individually resumable, and a
    reparse is cheaper to reason about than a half-written result.
    """
    await db.execute(delete(JobPage).where(JobPage.job_id == job_id))
    await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "running")
        .values(status="queued", started_at=None, pages_done=0)
    )
    await db.commit()
