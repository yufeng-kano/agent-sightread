# Project structure

```text
agent-sightread/
  apps/
    api/                      # FastAPI app + worker (one uv project, one image)
      src/sightread/
        main.py               # FastAPI wiring: /v1, /api, /oauth, /mcp, /.well-known
        config.py             # env settings (pydantic-settings)
        db/                   # engine, models, session helpers
        auth/                 # oidc.py, sessions.py, api_keys.py, oauth_as.py, crypto.py
        routes/               # v1.py (data plane), control.py (/api), oauth.py
        parsing/              # poppler.py (subprocess wrappers), route.py (text_layer vs vision),
                              # images.py (heic/exif/downscale), profiles.py, markdown.py
        upstream/             # openrouter.py (httpx client, usage capture, backoff)
        jobs/                 # queue.py (claim/enqueue), runner.py, sweeper.py, events.py (SSE)
        mcp/                  # thin shell over the service layer (docs/mcp.md)
        worker.py             # `python -m sightread.worker`
      migrations/             # Alembic
      tests/
      pyproject.toml          # uv-managed
      Dockerfile              # includes poppler-utils
    web/                      # Nuxt control plane (docs/web.md)
      app/ or src/            # Nuxt conventions; i18n/ catalog en + zh-TW
      package.json
      Dockerfile
  deploy/
    caddy/Caddyfile           # production routing + TLS
  docs/
  docker-compose.yaml             # local full stack (pg + api + worker + web), HTTP, ports exposed
  docker-compose.production.yaml  # standalone file (-f), adds caddy/TLS/env; NOT an override merge
  .env.example                # every env var with placeholder values
  LICENSE                     # MIT
```

## Boundaries

- `routes/*` and `mcp/*` are thin: validation + auth + calls into `jobs`/`parsing` services. MCP owns zero business logic.
- `parsing/poppler.py` is the **only** place that spawns Poppler; everything else consumes its typed results. No PDF library imports anywhere (AGPL ban, [parsing.md](./parsing.md)).
- `upstream/openrouter.py` is the only module that talks to OpenRouter and the only one that ever holds a decrypted user key.
- `jobs/queue.py` is the only module that knows the queue is Postgres.
- Web: pages thin, logic in composables; API access through one typed client module.
