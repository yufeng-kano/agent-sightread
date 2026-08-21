# API

Two planes, one FastAPI app:

- **Data plane `/v1/*`** — authenticated by API key (`Authorization: Bearer sr_...`) or an OAuth access token ([auth.md](./auth.md)). This is the product. `POST /v1/parse` and the three `GET /v1/jobs/{id}*` routes additionally accept a single-use upload ticket (`srt_...`, [auth.md](./auth.md) § 5): one upload, then reads of the job that upload created, nothing else.
- **Control plane `/api/*`** — session cookie (Google OIDC), consumed only by the Nuxt web app.

`GET /healthz` is public and DB-free (`{"ok": true}`). It backs the compose healthchecks and is also routed to the API on the public origin, so an external monitor can reach it — Caddy's `@api` matcher includes it explicitly ([deployment.md](./deployment.md)). All responses are JSON unless SSE is requested. Errors use one shape:

```json
{ "error": { "type": "invalid_request | auth | rate_limit | payment | upstream | internal", "message": "..." } }
```

## Data plane

### POST /v1/parse

Multipart form (preferred) or JSON with base64 `source`.

| Field | Notes |
|-------|-------|
| `file` | required; PDF or image (jpg/png/webp/heic). Max **128 MB** (`UPLOAD_MAX_BYTES`), PDFs max **500 pages** (`PAGE_CAP`) |
| `model` | optional OpenRouter model id; default from user settings |
| `profile` | optional preset profile id; mutually exclusive with raw `model` + `bbox_prompt` overrides ([parsing.md](./parsing.md)) |
| `pages` | optional selection, e.g. `"1-5,8"`; default all |
| `force` | optional bool; bypass dedup cache |

Responses:

- **200** — dedup cache hit ([jobs.md](./jobs.md) § Dedup): full result immediately.
- **202** — `{ "job_id": "...", "status": "queued" }`.
- With `Accept: text/event-stream` — SSE stream (below) instead; small documents feel synchronous.

The upload is hashed (SHA-256) while streaming to disk; the request must never buffer the whole file in memory.

### GET /v1/jobs/{id} — status

`{ job_id, status: queued|running|succeeded|failed, page_count, pages_done, error?, created_at, finished_at? }`

### GET /v1/jobs/{id}/result — full result

```json
{
  "markdown": "…",
  "pages":   [ { "page": 1, "width_pt": 612, "height_pt": 792, "method": "text_layer|vision", "error": null } ],
  "figures": [ { "id": "fig1", "page": 3, "bbox": [120, 60, 480, 940], "caption": "Figure 1: …" } ],
  "errors":  [ { "page": 7, "reason": "render failed" } ],
  "meta": {
    "model": "google/gemini-…",
    "profile": "gemini-yxyx",
    "bbox_format": "yxyx_norm1000",
    "pipeline_version": 1,
    "sha256": "…",
    "cached": false
  }
}
```

Figure placeholders in markdown: `![fig1](sightread://p3/120,60,480,940)` with the caption verbatim on the next line. Cropping is the caller's job (add ~2% margin; denormalize `x_px = x/1000 * page_width_px`).

### GET /v1/jobs/{id}/events — SSE progress

Events: `progress` (`{pages_done, page_count, page, method}` per finished page), then exactly one of `done` (full result payload) / `error`. Reconnectable at any time; a terminal job replays the final event immediately. Keepalive comment every 10 s.

### GET /v1/models

Also accepts a web session cookie (with `GET /v1/profiles`, the two read-only routes the web app may call on the data plane). OpenRouter model catalog filtered to `architecture.input_modalities` containing `"image"`, cached server-side ~1 h. Each entry carries `recommended: true` when a preset profile targets it. Never hard-code model ids.

### GET /v1/profiles

Preset profiles (id, name, model, bbox_format, description).

## Control plane (session cookie, CSRF-safe: SameSite=Lax + custom header check on mutations)

| Route | Purpose |
|-------|---------|
| `GET /api/auth/login` → Google, `GET /api/auth/callback`, `POST /api/auth/logout` | OIDC flow ([auth.md](./auth.md)) |
| `GET /api/me` | current user + settings + whether an OpenRouter key is stored (masked, never the value) |
| `GET/POST /api/keys`, `DELETE /api/keys/{id}` | API keys; `POST` returns the created key (with plaintext) exactly once, unwrapped; `GET` wraps as `{keys: []}` |
| `GET/PUT/DELETE /api/openrouter-key` | read masked form / store (validated against `GET https://openrouter.ai/api/v1/key` before save) / remove |
| `PUT /api/settings` | default model / profile |
| `GET /api/usage?days=30` | per-day and per-model aggregates of tokens + cost from `usage_log` |
| `GET /api/jobs?limit=50` | recent jobs (history): `job_id`, `kind`, `filename`, `status`, `model`, `profile`, `page_count`, `pages_done`, `error`, timestamps — no per-job cost (usage is aggregated per day/model only); `GET /api/jobs/{id}/result` same payload as data plane |

## Limits (defaults, env-overridable)

- `UPLOAD_MAX_BYTES` = 134217728 (128 MB) — enforced in the app **and** in Caddy; keep in sync ([deployment.md](./deployment.md)).
- `PAGE_CAP` = 500, `MAX_JOBS_PER_USER` = 2 concurrent, `VISION_CONCURRENCY_PER_JOB` = 8.
- 429 with `Retry-After` when the per-user job cap is hit; upstream 402 (OpenRouter credits exhausted) maps to `payment` and fails only the affected pages.
