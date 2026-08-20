# agent-sightread

Vision document parsing as a service: PDF or image in, markdown with figure coordinates out.

- Bring your own [OpenRouter](https://openrouter.ai) key — every vision call bills your account, not the operator's.
- REST first (`POST /v1/parse`), with a hosted MCP endpoint on top that works as a Claude custom connector (OAuth, no key pasting).
- Figures come back as coordinates (`![fig1](sightread://p3/120,60,480,940)`, `[ymin,xmin,ymax,xmax]` normalized 0–1000) — you crop, we don't.
- Text-layer pages convert for free; only visually hard pages hit the vision model.
- FastAPI + PostgreSQL + Poppler + Nuxt, deployed with docker-compose behind Caddy.

## Quick start (local)

```bash
cp .env.example .env
docker compose up --build
```

Web UI at http://localhost:3000, API at http://localhost:8000. `AUTH_DEV_MODE=true` in `.env` lets you sign in locally without Google credentials.

## Docs

Start at [docs/index.md](docs/index.md). License: [MIT](LICENSE).
