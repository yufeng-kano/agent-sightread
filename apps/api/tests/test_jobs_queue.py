"""Queue behaviour: page specs, dedup lookup, claiming and the retention sweeper.

The `SKIP LOCKED` claim can only be exercised on PostgreSQL, so those tests skip unless
`TEST_DATABASE_URL` points at one (docs/testing.md).
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import timedelta

import pytest

from sightread.db.models import Job, User, utcnow
from sightread.jobs.queue import (
    claim_next_job,
    count_running_jobs,
    enqueue_job,
    find_cached_job,
    normalize_pages_spec,
    parse_pages_spec,
    requeue_job,
)
from sightread.jobs.sweeper import MAX_AGE_SECONDS, sweep_uploads
from tests.conftest import DATABASE_URL

postgres_only = pytest.mark.skipif(
    not (DATABASE_URL or "").startswith("postgresql"),
    reason="needs TEST_DATABASE_URL pointing at PostgreSQL",
)

JOB_DEFAULTS = {
    "kind": "pdf",
    "filename": "paper.pdf",
    "media_type": "application/pdf",
    "size_bytes": 2048,
    "pages_spec": "",
    "model": "vendor/model",
    "profile": None,
    "profile_version": 0,
    "bbox_format": "yxyx_norm1000",
    "page_count": 2,
}


async def _user(db, email: str = "queue@example.com") -> User:
    user = User(google_sub=email, email=email)
    db.add(user)
    await db.flush()
    return user


def test_parse_pages_spec() -> None:
    assert parse_pages_spec("", 3) == [1, 2, 3]
    assert parse_pages_spec("1-3,5", 8) == [1, 2, 3, 5]
    assert parse_pages_spec("2,2,1", 8) == [1, 2]
    assert normalize_pages_spec(" 1 - 3 , 5 ") == "1-3,5"

    for bad in ("1-", "a", "0", "3-1", "9"):
        with pytest.raises(ValueError):
            parse_pages_spec(bad, 8)


async def test_dedup_lookup_matches_the_full_key(sessionmaker) -> None:
    async with sessionmaker() as db:
        user = await _user(db)
        job = await enqueue_job(
            db, user_id=user.id, sha256="a" * 64, source_path="unused-a.pdf", **JOB_DEFAULTS
        )
        job.status = "succeeded"
        await db.commit()

        key = {
            "user_id": user.id,
            "sha256": "a" * 64,
            "model": "vendor/model",
            "profile": None,
            "profile_version": 0,
            "pages_spec": "",
        }
        assert (await find_cached_job(db, **key)).id == job.id
        assert await find_cached_job(db, **{**key, "sha256": "b" * 64}) is None
        assert await find_cached_job(db, **{**key, "model": "other/model"}) is None
        assert await find_cached_job(db, **{**key, "pages_spec": "1-2"}) is None
        assert await find_cached_job(db, **{**key, "profile": "gemini-yxyx"}) is None

        other = await _user(db, "second@example.com")
        # Never across users, even for identical bytes (docs/jobs.md § Dedup).
        assert await find_cached_job(db, **{**key, "user_id": other.id}) is None


async def test_dedup_ignores_unfinished_jobs(sessionmaker) -> None:
    async with sessionmaker() as db:
        user = await _user(db)
        await enqueue_job(
            db, user_id=user.id, sha256="c" * 64, source_path="unused-c.pdf", **JOB_DEFAULTS
        )
        await db.commit()

        assert (
            await find_cached_job(
                db,
                user_id=user.id,
                sha256="c" * 64,
                model="vendor/model",
                profile=None,
                profile_version=0,
                pages_spec="",
            )
            is None
        )


async def test_claim_is_fifo_and_marks_the_job_running(sessionmaker) -> None:
    async with sessionmaker() as db:
        user = await _user(db)
        first = await enqueue_job(
            db, user_id=user.id, sha256="1" * 64, source_path="unused-1.pdf", **JOB_DEFAULTS
        )
        second = await enqueue_job(
            db, user_id=user.id, sha256="2" * 64, source_path="unused-2.pdf", **JOB_DEFAULTS
        )
        second.created_at = first.created_at + timedelta(seconds=5)
        await db.commit()

    async with sessionmaker() as db:
        claimed = await claim_next_job(db, max_jobs_per_user=2)
    assert claimed == first.id

    async with sessionmaker() as db:
        assert (await db.get(Job, first.id)).status == "running"
        assert await count_running_jobs(db, first.user_id) == 1


async def test_claim_honours_the_per_user_cap(sessionmaker) -> None:
    async with sessionmaker() as db:
        user = await _user(db)
        running = await enqueue_job(
            db, user_id=user.id, sha256="3" * 64, source_path="unused-3.pdf", **JOB_DEFAULTS
        )
        running.status = "running"
        await enqueue_job(
            db, user_id=user.id, sha256="4" * 64, source_path="unused-4.pdf", **JOB_DEFAULTS
        )
        await db.commit()

    async with sessionmaker() as db:
        assert await claim_next_job(db, max_jobs_per_user=1) is None
    async with sessionmaker() as db:
        assert await claim_next_job(db, max_jobs_per_user=2) is not None


async def test_requeue_forgets_partial_progress(sessionmaker) -> None:
    async with sessionmaker() as db:
        user = await _user(db)
        job = await enqueue_job(
            db, user_id=user.id, sha256="5" * 64, source_path="unused-5.pdf", **JOB_DEFAULTS
        )
        job.status = "running"
        job.pages_done = 1
        job.started_at = utcnow()
        await db.commit()
        job_id = job.id

    async with sessionmaker() as db:
        await requeue_job(db, job_id)
    async with sessionmaker() as db:
        requeued = await db.get(Job, job_id)
        assert (requeued.status, requeued.pages_done, requeued.started_at) == ("queued", 0, None)


@postgres_only
async def test_two_claimers_never_take_the_same_job(sessionmaker) -> None:
    async with sessionmaker() as db:
        user = await _user(db)
        for index in range(2):
            await enqueue_job(
                db,
                user_id=user.id,
                sha256=str(index) * 64,
                source_path=f"unused-{index}.pdf",
                **JOB_DEFAULTS,
            )
        await db.commit()

    async def claim() -> uuid.UUID | None:
        async with sessionmaker() as db:
            return await claim_next_job(db, max_jobs_per_user=2)

    first, second = await asyncio.gather(claim(), claim())

    assert first is not None and second is not None
    assert first != second


def test_sweeper_removes_only_stale_entries(tmp_path) -> None:
    fresh = tmp_path / "fresh.pdf"
    fresh.write_bytes(b"x")
    stale = tmp_path / "stale.pdf"
    stale.write_bytes(b"x")
    stale_dir = tmp_path / "abandoned-job"
    stale_dir.mkdir()
    (stale_dir / "page-1.png").write_bytes(b"x")

    old = time.time() - MAX_AGE_SECONDS - 60
    for entry in (stale, stale_dir):
        os.utime(entry, (old, old))

    assert sweep_uploads(tmp_path) == 2
    assert fresh.exists()
    assert not stale.exists()
    assert not stale_dir.exists()
