# agent-sightread

Guardrails only — `docs/` is the source of truth for details.

## Docs first

- Before non-trivial work, read `docs/index.md` and the linked docs matching the task.
- Feature/schema/behavior changes: update `docs/` first, then implement (small obvious fixes exempt). Keep `docs/index.md` in sync.
- If a request conflicts with docs, state the conflict and wait for docs or an explicit override.

## Cost safety — user OpenRouter keys are real money

- Never debug, reproduce, or benchmark by sending real requests to OpenRouter or any paid upstream. Verification is unit tests with stubbed HTTP (`docs/testing.md`).
- A live smoke test needs explicit per-instance approval: one tiny document, one cheap model, never a loop.

## Secrets

- Never commit secrets. Real values live in `.env` (gitignored); tracked files use placeholders. Never print secret values — only whether one exists.
- Credentials at rest per `docs/auth.md`: hash what we only verify, AES-GCM what we must replay. No plaintext anywhere, including logs and error messages.

## Hard technical rules

- PDF work only via Poppler CLI subprocesses (`docs/parsing.md`). **No PyMuPDF / no linked PDF libraries** (AGPL).
- Queue is PostgreSQL `FOR UPDATE SKIP LOCKED` (`docs/jobs.md`). No Redis, no broker.
- Uploads stream to disk with size caps; never buffer whole files in memory. No `file path` source on hosted endpoints.
- Uploads and SSE bypass the Nuxt server entirely (`docs/deployment.md`).
- Schema changes only via Alembic migrations, `docs/database.md` updated first.
- Python via uv (`uv run`, `uv add`); code, comments, identifiers in English; UI copy through the i18n catalog (en + zh-TW).

## Real data only

- Frontend renders only what the backend returns; empty is a real state. Never hard-code model ids, usage numbers, or sample documents as if live — models come from OpenRouter's catalog, usage from `usage_log`. Exceptions: test fixtures in `tests/`, docs examples with placeholders.
