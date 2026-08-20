# Deployment

Single server, docker-compose, Caddy in front. Environments: **local** and **production** only. Production host/DNS specifics stay out of tracked files (use `.local/` notes if needed; this repo is public).

## Two standalone compose files (no override merging)

Compose `-f` merge semantics surprise people; each file is complete and readable on its own.

### `docker-compose.yaml` — local

- Services: `pg`, `api`, `worker`, `web`. No Caddy, plain HTTP, ports exposed: web `3000`, api `8000`, pg `5432` (localhost only).
- `env_file: .env` (copy from `.env.example`); `APP_ENV=local`, `AUTH_DEV_MODE=true` works here so the stack is demoable without Google credentials.
- Volumes: `pgdata`, `uploads` (shared by api + worker).
- Day-to-day dev still runs `uv run uvicorn` / `pnpm dev` natively for hot reload; the compose file is for integration runs.

### `docker-compose.production.yaml` — used as `docker compose -f docker-compose.production.yaml up -d`

- Adds `caddy` (ports 80/443, automatic TLS via ACME); `api`/`web` not published on the host, reachable only on the compose network.
- `APP_ENV=production` (dev login hard-disabled), `AUTH_DEV_MODE` absent.
- Volumes: `pgdata`, `uploads`, `caddy_data` (certs), `caddy_config`.
- Backups: a `pg_dump` sidecar/cron writing rotating dumps to a mounted path — restore procedure tested before launch. Leaving managed platforms means backups are ours now.

## Caddy routing (`deploy/caddy/Caddyfile`)

```text
<domain> {
  request_body { max_size 128MB }        # keep in sync with UPLOAD_MAX_BYTES
  @api path /v1/* /api/* /oauth/* /mcp /mcp/* /.well-known/*
  handle @api { reverse_proxy api:8000 }
  handle      { reverse_proxy web:3000 }
}
```

Uploads and SSE go straight through Caddy to FastAPI — never through the Nuxt/Node server. Disable proxy buffering for SSE routes; long-lived connections need generous idle timeouts.

## Environment variables (`.env.example` is the authoritative list)

| Var | Notes |
|-----|-------|
| `APP_ENV` | `local` / `production` |
| `APP_URL` | public origin, used in OAuth metadata + OIDC redirect |
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `SECRET_KEY` | sessions + HKDF root for OpenRouter-key encryption; generate long random |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OIDC |
| `AUTH_DEV_MODE` | local only |
| `UPLOAD_MAX_BYTES`, `PAGE_CAP`, `MAX_JOBS_PER_USER`, `VISION_CONCURRENCY_PER_JOB`, `RENDER_WORKERS` | defaults in [api.md](./api.md) / [jobs.md](./jobs.md) |
| `UPLOAD_DIR` | `/data/uploads` in containers |
| `PG_PORT` | local compose only: host port for `pg` (default 5432); change it when that port is taken |

Secrets live in `.env` (gitignored) on the server; tracked files carry placeholders only. Never print secret values — only whether one exists.

## Release flow (initial)

`git pull && docker compose -f docker-compose.production.yaml up -d --build` on the server. Tagged releases/CI can come later; keep root `package.json` version bumped per SemVer when tagging starts.
