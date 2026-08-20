# Jobs: queue, concurrency, dedup, retention

## Queue = PostgreSQL, nothing else

Jobs are rows in `jobs`. The worker claims work with:

```sql
UPDATE jobs SET status='running', started_at=now()
WHERE id = (
  SELECT id FROM jobs WHERE status='queued'
  ORDER BY created_at
  FOR UPDATE SKIP LOCKED LIMIT 1
) RETURNING *;
```

Enqueue happens in the **same transaction** as job-row creation — no dual-write problem, no broker. If a queue swap (e.g. RabbitMQ) ever happens, it happens behind the small `queue` module interface; nothing else may know how claiming works.

The worker is the same codebase as the API, launched as its own process/container (`python -m sightread.worker`). Rendering runs in Poppler subprocesses (multi-core comes free); vision calls fan out per page with an asyncio semaphore.

## Concurrency caps (defaults)

- `MAX_JOBS_PER_USER` = 2 running jobs; excess `POST /v1/parse` gets 429 + `Retry-After` (fail closed, never crash).
- `VISION_CONCURRENCY_PER_JOB` = 8 concurrent OpenRouter calls.
- `RENDER_WORKERS` = CPU count (env-overridable) concurrent Poppler subprocesses per worker.

Fairness: the claim query above is FIFO; per-user cap is enforced at claim time too (skip a queued job whose user already has `MAX_JOBS_PER_USER` running).

## Progress

Worker updates `jobs.pages_done` and `job_pages` rows as pages finish; SSE endpoints read from PG (LISTEN/NOTIFY for wakeup, poll fallback). Terminal jobs replay their final event on reconnect.

## Dedup cache

Key: `(user_id, sha256, model, profile, profile_version, pages_spec, PIPELINE_VERSION)`.

- On `POST /v1/parse`, hash while streaming to disk; if a **succeeded** job matches the full key and `force` is not set → return its result immediately (200, `meta.cached: true`), delete the fresh upload, create no job.
- **Per-user only.** Never dedup across users: it would spend one user's OpenRouter output on another and leak that a document was parsed before.
- `force: true` always reparses (result row is replaced).

## Retention — two layers, sweeper is the guarantee

1. **Immediate:** source file (and rendered page images) deleted the moment a job reaches `succeeded`/`failed`. After that, reparsing requires re-upload — accepted trade-off, documented here on purpose.
2. **Sweeper:** periodic task inside the worker (every 15 min) trashes anything under the upload dir older than 24 h — catches crashed jobs, abandoned uploads, bugs. The sweeper is the guarantee; immediate deletion is an optimization.

Results (markdown + metadata in PG) are kept **indefinitely** for now (low traffic); revisit when storage says otherwise. Usage rows are permanent — they are the billing history.
