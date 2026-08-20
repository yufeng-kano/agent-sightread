"""SSE progress streams (docs/api.md § events, docs/jobs.md § Progress).

The database is the only source of truth: `NOTIFY` merely wakes a stream up, and a stream
that never hears a notification still makes progress by polling. That keeps the contract
identical on a backend without LISTEN/NOTIFY, and makes a missed notification a latency
problem rather than a correctness one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator

import asyncpg
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import Job, JobPage, Result

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 1.0
TERMINAL_STATUSES = ("succeeded", "failed")


def channel_for(job_id: uuid.UUID) -> str:
    """One channel per job, so a stream is only woken by its own job."""
    return f"sr_job_{job_id.hex}"


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def notify(db: AsyncSession, job_id: uuid.UUID) -> None:
    """Wake every stream watching this job, when the backend can do it."""
    if db.get_bind().dialect.name != "postgresql":
        return
    await db.execute(text("SELECT pg_notify(:channel, '')"), {"channel": channel_for(job_id)})


async def _open_listener(database_url: str, job_id: uuid.UUID, wakeup: asyncio.Event):
    """A dedicated PostgreSQL connection listening for this job, or None.

    Deliberately outside the SQLAlchemy pool: an SSE stream lives as long as its client,
    and long-lived listeners must not eat the connections the API needs to answer requests.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        return None
    try:
        connection = await asyncpg.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False)
        )
        await connection.add_listener(channel_for(job_id), lambda *_: wakeup.set())
    except (OSError, asyncpg.PostgresError):
        logger.warning("job event listener unavailable; falling back to polling")
        return None
    return connection


async def _snapshot(sessionmaker: async_sessionmaker[AsyncSession], job_id: uuid.UUID):
    """Job row plus the pages that have finished so far."""
    async with sessionmaker() as db:
        job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
        if job is None:
            return None, [], None
        pages = (
            (
                await db.execute(
                    select(JobPage).where(JobPage.job_id == job_id).order_by(JobPage.page_no)
                )
            )
            .scalars()
            .all()
        )
        result = None
        if job.status in TERMINAL_STATUSES:
            result = (
                await db.execute(select(Result).where(Result.job_id == job_id))
            ).scalar_one_or_none()
        return job, list(pages), result


async def stream_job_events(
    sessionmaker: async_sessionmaker[AsyncSession],
    database_url: str,
    job_id: uuid.UUID,
) -> AsyncIterator[str]:
    """Yield SSE frames until the job reaches a terminal state.

    A job that is already terminal replays its final event immediately, so a client that
    reconnects late still gets its result.
    """
    # Imported here: the runner imports this module for `notify`, and the result shape
    # belongs to the runner that writes it.
    from .runner import result_payload

    wakeup = asyncio.Event()
    listener = await _open_listener(database_url, job_id, wakeup)
    emitted: set[int] = set()
    silent_for = 0.0

    try:
        while True:
            job, pages, result = await _snapshot(sessionmaker, job_id)
            if job is None:
                yield sse("error", {"error": {"type": "invalid_request", "message": "No such job"}})
                return

            for page in pages:
                if page.page_no in emitted:
                    continue
                emitted.add(page.page_no)
                silent_for = 0.0
                yield sse(
                    "progress",
                    {
                        "pages_done": job.pages_done,
                        "page_count": job.page_count,
                        "page": page.page_no,
                        "method": page.method,
                    },
                )

            if job.status in TERMINAL_STATUSES:
                if result is not None:
                    yield sse("done", result_payload(result))
                else:
                    yield sse(
                        "error",
                        {"error": {"type": "internal", "message": job.error or "Job failed"}},
                    )
                return

            wakeup.clear()
            try:
                await asyncio.wait_for(wakeup.wait(), timeout=POLL_INTERVAL_SECONDS)
                silent_for = 0.0
            except TimeoutError:
                silent_for += POLL_INTERVAL_SECONDS
                if silent_for >= KEEPALIVE_SECONDS:
                    silent_for = 0.0
                    yield ": keepalive\n\n"
    finally:
        if listener is not None:
            await listener.close()
