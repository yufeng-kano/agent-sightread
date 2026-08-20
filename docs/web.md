# Web (Nuxt control plane)

The web app is a **pure control plane**: configure, issue, observe. It never uploads, previews, or renders documents — the data plane is API/MCP only.

## Stack

Nuxt (latest stable) + TypeScript + `@nuxtjs/i18n` (en, zh-TW; en is the source catalog), pnpm. No heavy UI framework — hand-rolled primitives, design restraint in the kano-proxy spirit: one surface, icons over restated copy, no decorative cards.

## Pages

| Page | Rendering | Content |
|------|-----------|---------|
| `/` landing | **prerendered, public** (en + `/zh-TW`, hreflang) — the SEO surface: meta tags, OG. Sitemap deferred: needs the public origin (`i18n.baseUrl`), configure when a host exists | what the service is, how the API/connector works, link to sign in |
| `/dashboard` | client-side, authed | usage: cost + tokens per day and per model (`GET /api/usage`) |
| `/keys` | client-side, authed | API key list/create/revoke; plaintext shown once; MCP endpoint URL + "add to Claude" instructions |
| `/settings` | client-side, authed | OpenRouter key (masked, save validates upstream), default model (from `GET /v1/models`, recommended profiles first), default profile |
| `/jobs` | client-side, authed | parse history: filename, status, model, pages, expandable raw result JSON (per-job cost not exposed yet — usage aggregates only) |

## Rules

- Auth state via `GET /api/me`; unauthenticated → landing. Login is a plain link to `/api/auth/login` (server redirect flow, no client OAuth).
- The web app calls only `/api/*` (+ `GET /v1/models`, `GET /v1/profiles` which are safe reads). Session cookie, `credentials: include`, custom `X-Requested-With` header on mutations (CSRF pairing with SameSite=Lax).
- Frontend renders only what the backend returns — empty states are real states, never fabricated sample data.
- Uploads never pass through Nuxt/Node — there is no upload UI; docs on the landing page point at `curl`/connector usage instead.
- i18n: every user-visible string goes through the catalog; en and zh-TW ship together.
