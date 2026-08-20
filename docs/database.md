# Database

PostgreSQL 16+. Schema changes **only** via Alembic migrations under `apps/api/migrations/`, this doc updated first. Never edit production schema by hand.

## Tables

```text
users            id PK, google_sub UNIQUE, email, name, created_at
sessions         id PK, user_id FK, token_hash UNIQUE, created_at, expires_at
api_keys         id PK, user_id FK, name, key_hash UNIQUE, prefix, created_at,
                 last_used_at, revoked_at NULL
openrouter_keys  user_id PK/FK, ciphertext BYTEA, masked, updated_at        -- one per user
user_settings    user_id PK/FK, default_model, default_profile
jobs             id UUID PK, user_id FK, kind pdf|image, filename, media_type,
                 size_bytes, sha256, pages_spec, model, profile, profile_version,
                 pipeline_version, bbox_format,
                 status queued|running|succeeded|failed, error,
                 page_count, pages_done, source_path NULL, source_deleted_at NULL,
                 created_at, started_at, finished_at
                 INDEX (status, created_at)                                  -- queue claim
                 INDEX (user_id, sha256, model, profile, profile_version,
                        pages_spec, pipeline_version) WHERE status='succeeded' -- dedup
job_pages        (job_id FK, page_no) PK, method NULL, status, error NULL
results          job_id PK/FK, markdown TEXT, pages JSONB, figures JSONB,
                 errors JSONB, meta JSONB, created_at
usage_log        id PK, user_id FK, job_id FK, model, prompt_tokens,
                 completion_tokens, cost NUMERIC(12,6), created_at
                 INDEX (user_id, created_at)
oauth_clients    client_id PK, client_name, redirect_uris JSONB, created_at
oauth_grants     id PK, client_id FK, user_id FK, kind code|access|refresh,
                 token_hash UNIQUE, pkce_challenge NULL, scope, expires_at,
                 revoked_at NULL, created_at
```

## Rules

- All credentials at rest follow [auth.md](./auth.md): hashes for anything we only verify, AES-GCM ciphertext for the one thing we must replay (OpenRouter key). No plaintext secrets in any column.
- `results` holds parsed **output** (kept indefinitely); `jobs.source_path` points at a temp file that is deleted at terminal state — the DB never stores document bytes.
- Job claiming and per-user caps: exact queries in [jobs.md](./jobs.md).
- Timestamps are `timestamptz`, UTC.
