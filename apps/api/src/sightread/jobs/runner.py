"""Job execution: one document, page by page (docs/jobs.md, docs/parsing.md).

Shape of a run: read the job, resolve the user's key, work out the pages, then fan the
pages out. Poppler work is bounded by the worker-wide render semaphore; upstream calls are
bounded by this job's own vision budget, which halves itself when OpenRouter says 429.

Page failures are page-scoped by design: an unreadable page becomes an entry in `errors`
and the rest of the document still parses. Only a document where no page survived, a dead
key, or exhausted credits ends the whole job.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..db.models import Job, JobPage, Result, UsageLog, utcnow
from ..parsing import poppler
from ..parsing.images import ImageError, normalize_image
from ..parsing.markdown import PageMarkdown, assemble
from ..parsing.profiles import transcription_prompt_template
from ..upstream.openrouter import (
    PaymentRequired,
    RateLimited,
    UpstreamError,
    Usage,
    UserKey,
    load_user_key,
    transcribe_page,
)
from . import events
from .queue import parse_pages_spec

logger = logging.getLogger(__name__)

# 429 retry policy for one upstream call (docs/parsing.md § OpenRouter usage).
VISION_MAX_ATTEMPTS = 4
VISION_BACKOFF_BASE_SECONDS = 1.0

# A second 402 without an intervening success means the key is dead, not the page.
PAYMENT_FAILURES_BEFORE_ABORT = 2


class JobAborted(Exception):
    """A failure that ends the whole job rather than one page."""


class VisionBudget:
    """Per-job concurrency limit that can shrink while the job runs.

    A plain semaphore cannot give permits back to nobody, and 429 handling requires
    exactly that: after a rate limit the job must keep running, more slowly.
    """

    def __init__(self, limit: int) -> None:
        self._limit = max(1, limit)
        self._in_flight = 0
        self._condition = asyncio.Condition()

    @property
    def limit(self) -> int:
        return self._limit

    @asynccontextmanager
    async def slot(self):
        async with self._condition:
            await self._condition.wait_for(lambda: self._in_flight < self._limit)
            self._in_flight += 1
        try:
            yield
        finally:
            async with self._condition:
                self._in_flight -= 1
                self._condition.notify_all()

    async def halve(self) -> None:
        async with self._condition:
            self._limit = max(1, self._limit // 2)


# The one conversion method (docs/parsing.md § Vision-only conversion).
VISION = "vision"


@dataclass
class PageOutcome:
    page: int
    width_pt: float
    height_pt: float
    method: str | None = None
    error: str | None = None
    markdown: str = ""
    usage: list[Usage] = field(default_factory=list)


@dataclass
class RunState:
    """Cross-page state for one run: what the fan-out has to agree about."""

    budget: VisionBudget
    payment_failures: int = 0


def result_payload(result: Result) -> dict:
    """The result shape both planes return (docs/api.md § GET /v1/jobs/{id}/result)."""
    return {
        "markdown": result.markdown,
        "pages": result.pages,
        "figures": result.figures,
        "errors": result.errors,
        "meta": result.meta,
    }


def job_prompt(job: Job) -> str:
    """The transcription prompt template this job runs.

    The effective template is stored on the row at enqueue time (docs/parsing.md §
    Prompts); jobs from before that column exist resolve their profile's template again.
    """
    return job.prompt or transcription_prompt_template(job.profile)


async def _call_upstream(state: RunState, call):
    """Run one upstream call under the job's budget, backing off on 429.

    Each rate limit also halves this job's concurrency, so a job that is being throttled
    stops fighting the throttle.
    """
    for attempt in range(VISION_MAX_ATTEMPTS):
        async with state.budget.slot():
            try:
                return await call()
            except RateLimited as exc:
                if attempt == VISION_MAX_ATTEMPTS - 1:
                    raise
                delay = exc.retry_after or VISION_BACKOFF_BASE_SECONDS * (2**attempt)
        await state.budget.halve()
        await asyncio.sleep(delay)
    raise RateLimited()


async def _guarded_call(state: RunState, outcome: PageOutcome, call):
    """Apply the upstream failure policy of docs/parsing.md to one page.

    Returns the call's result, or None when the page failed — the failure is already
    recorded on the outcome. Failures that will repeat for every page abort the job.
    """
    try:
        result = await _call_upstream(state, call)
    except PaymentRequired:
        state.payment_failures += 1
        if state.payment_failures >= PAYMENT_FAILURES_BEFORE_ABORT:
            raise JobAborted("OpenRouter reported exhausted credits") from None
        outcome.error = "payment"
        return None
    except RateLimited:
        outcome.error = "rate limited"
        return None
    except UpstreamError as exc:
        if exc.fatal:
            raise JobAborted("OpenRouter rejected the stored key") from None
        outcome.error = "upstream call failed"
        return None

    state.payment_failures = 0
    outcome.usage.append(result.usage)
    return result


async def _process_pdf_page(
    job: Job,
    state: RunState,
    key: UserKey,
    info: poppler.PdfInfo,
    page_no: int,
    source: Path,
    work_dir: Path,
    render_slots: asyncio.Semaphore,
) -> PageOutcome:
    size = info.page_size(page_no)
    outcome = PageOutcome(
        page=page_no, width_pt=size.width_pt, height_pt=size.height_pt, method=VISION
    )

    try:
        async with render_slots:
            image = await poppler.render_page(source, page_no, size, cwd=work_dir)
    except poppler.PopplerError as exc:
        # The Poppler detail is diagnostic (its stderr), never document content.
        logger.warning("job %s page %d render failed: %s", job.id, page_no, exc)
        outcome.error = "render failed"
        return outcome

    try:
        transcription = await _guarded_call(
            state,
            outcome,
            lambda: transcribe_page(
                key, job.model, job_prompt(job), job.bbox_format, image, page_no
            ),
        )
        if transcription is not None:
            outcome.markdown = transcription.markdown
    finally:
        # The rendered page has served its purpose; nothing may outlive the call.
        image.unlink(missing_ok=True)
    return outcome


async def _process_image(
    job: Job, state: RunState, key: UserKey, source: Path, work_dir: Path
) -> PageOutcome:
    try:
        normalized = normalize_image(source, work_dir)
    except ImageError:
        return PageOutcome(page=1, width_pt=0, height_pt=0, error="the image could not be decoded")

    outcome = PageOutcome(
        page=1,
        width_pt=float(normalized.width_px),
        height_pt=float(normalized.height_px),
        method=VISION,
    )
    try:
        transcription = await _guarded_call(
            state,
            outcome,
            lambda: transcribe_page(
                key, job.model, job_prompt(job), job.bbox_format, normalized.path, 1
            ),
        )
        if transcription is not None:
            outcome.markdown = transcription.markdown
    finally:
        normalized.path.unlink(missing_ok=True)
    return outcome


async def _record_page(
    sessionmaker: async_sessionmaker[AsyncSession], job: Job, outcome: PageOutcome
) -> None:
    """Persist one finished page: its row, the job's progress and the calls it billed."""
    async with sessionmaker() as db:
        db.add(
            JobPage(
                job_id=job.id,
                page_no=outcome.page,
                method=outcome.method,
                status="failed" if outcome.error else "succeeded",
                error=outcome.error,
            )
        )
        for usage in outcome.usage:
            db.add(
                UsageLog(
                    user_id=job.user_id,
                    job_id=job.id,
                    model=job.model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cost=usage.cost,
                )
            )
        await db.execute(update(Job).where(Job.id == job.id).values(pages_done=Job.pages_done + 1))
        await events.notify(db, job.id)
        await db.commit()


async def _finish(
    sessionmaker: async_sessionmaker[AsyncSession],
    job_id: uuid.UUID,
    *,
    status: str,
    error: str | None = None,
    result: dict | None = None,
) -> None:
    """Write the terminal state and delete the source document (docs/jobs.md § Retention)."""
    async with sessionmaker() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        if result is not None:
            db.add(
                Result(
                    job_id=job.id,
                    markdown=result["markdown"],
                    pages=result["pages"],
                    figures=result["figures"],
                    errors=result["errors"],
                    meta=result["meta"],
                )
            )
        job.status = status
        job.error = error
        job.finished_at = utcnow()
        if job.source_path:
            Path(job.source_path).unlink(missing_ok=True)
            job.source_deleted_at = utcnow()
        await events.notify(db, job.id)
        await db.commit()


async def run_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    job_id: uuid.UUID,
    render_slots: asyncio.Semaphore,
) -> None:
    """Drive one claimed job to a terminal state. Never raises for a document's own faults."""
    async with sessionmaker() as db:
        job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
        if job is None or job.status != "running":
            return
        key = await load_user_key(db, settings.secret_key, job.user_id)

    if key is None:
        await _finish(sessionmaker, job_id, status="failed", error="no OpenRouter key stored")
        return

    source = Path(job.source_path or "")
    work_dir = Path(settings.upload_dir) / str(job.id)
    work_dir.mkdir(parents=True, exist_ok=True)
    state = RunState(budget=VisionBudget(settings.vision_concurrency_per_job))

    try:
        outcomes = await _process_job(job, state, key, source, work_dir, render_slots, sessionmaker)
    except JobAborted as exc:
        await _finish(sessionmaker, job_id, status="failed", error=str(exc))
        return
    except (poppler.PopplerError, ImageError, ValueError):
        await _finish(sessionmaker, job_id, status="failed", error="the document is unreadable")
        return
    except Exception:
        # A worker must not die on one job. The traceback goes to the log; the job row
        # carries no internals and no document content.
        logger.exception("job %s failed unexpectedly", job_id)
        await _finish(sessionmaker, job_id, status="failed", error="internal error")
        return
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    if all(outcome.error for outcome in outcomes):
        # Partial markdown from a document nothing could read is worse than nothing, but
        # the caller still deserves to know what killed each page.
        reasons = "; ".join(f"page {o.page}: {o.error}" for o in outcomes[:5])
        if len(outcomes) > 5:
            reasons += "; …"
        await _finish(
            sessionmaker, job_id, status="failed", error=f"no page could be parsed ({reasons})"
        )
        return

    document = assemble(
        [
            PageMarkdown(page=outcome.page, markdown=outcome.markdown)
            for outcome in outcomes
            if not outcome.error
        ]
    )
    if document.dropped_figures:
        # A count only: how badly the chosen model follows the coordinate contract is worth
        # knowing, what it said about the document is not.
        logger.info("job %s dropped %d unusable figure boxes", job_id, document.dropped_figures)
    await _finish(
        sessionmaker,
        job_id,
        status="succeeded",
        result={
            "markdown": document.markdown,
            "pages": [
                {
                    "page": outcome.page,
                    "width_pt": round(outcome.width_pt, 2),
                    "height_pt": round(outcome.height_pt, 2),
                    "method": outcome.method,
                    "error": outcome.error,
                }
                for outcome in outcomes
            ],
            "figures": document.figures,
            "errors": [
                {"page": outcome.page, "reason": outcome.error}
                for outcome in outcomes
                if outcome.error
            ],
            "meta": {
                "job_id": str(job.id),
                "model": job.model,
                "profile": job.profile,
                "bbox_format": job.bbox_format,
                "pipeline_version": job.pipeline_version,
                "sha256": job.sha256,
                "cached": False,
            },
        },
    )


async def _process_job(
    job: Job,
    state: RunState,
    key: UserKey,
    source: Path,
    work_dir: Path,
    render_slots: asyncio.Semaphore,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> list[PageOutcome]:
    """Fan the job's pages out and record each as it finishes."""
    if job.kind == "image":
        outcome = await _process_image(job, state, key, source, work_dir)
        await _record_page(sessionmaker, job, outcome)
        return [outcome]

    info = await poppler.pdf_info(source, cwd=work_dir)
    page_numbers = parse_pages_spec(job.pages_spec, info.page_count)

    outcomes: dict[int, PageOutcome] = {}

    async def process(page_no: int) -> None:
        outcome = await _process_pdf_page(
            job, state, key, info, page_no, source, work_dir, render_slots
        )
        outcomes[page_no] = outcome
        await _record_page(sessionmaker, job, outcome)

    try:
        async with asyncio.TaskGroup() as group:
            for page_no in page_numbers:
                group.create_task(process(page_no))
    except* JobAborted as aborted:
        # One page hit a job-ending failure; the group has already cancelled the rest.
        raise JobAborted(str(aborted.exceptions[0])) from None
    return [outcomes[page_no] for page_no in page_numbers if page_no in outcomes]
