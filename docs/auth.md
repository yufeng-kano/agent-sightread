# Auth

Five credential kinds, strictly separated. No password login anywhere.

## 1. Web sessions — Google OIDC only

- `GET /api/auth/login` → Google (Authorization Code + PKCE); callback creates/updates the `users` row (keyed by Google `sub`) and a server-side session row; cookie is `HttpOnly; Secure; SameSite=Lax`, value is a random token stored **hashed** in `sessions`.
- Logout deletes the session row. Sessions expire (30 d) and are revocable server-side.
- Local dev only: `AUTH_DEV_MODE=true` **and** `APP_ENV=local` enables a `POST /api/auth/dev-login` that signs in as `dev@localhost` (returns `{user: {id, email}}`) — the route must hard-refuse to exist when `APP_ENV != local`. It is CSRF-guarded like every mutation, which lets the web app probe for it without creating a session (no header → 403; absent → 404).

## 2. Project API keys (data plane)

- Format `sr_<32 random url-safe chars>`; shown exactly once at creation; stored as SHA-256 hash + display prefix (`sr_...abc4`).
- Sent as `Authorization: Bearer sr_...` on `/v1/*`. Constant-time lookup by hash. Revocation = soft delete.

## 3. User's OpenRouter key — encrypted, never hashed (we must use it)

- AES-256-GCM, key derived from `SECRET_KEY` via HKDF (context string `openrouter-key-v1`), random nonce per encryption.
- Validated at save time with `GET https://openrouter.ai/api/v1/key` using the candidate key; invalid → 400, nothing stored.
- API/UI only ever return the masked form. The plaintext exists in memory only for the duration of an upstream call. **Never logged, never in error messages.**

## 4. OAuth 2.1 authorization server — for Claude Connectors

Claude custom connectors assume OAuth 2.1 on remote MCP servers and attempt Dynamic Client Registration; tokens in query strings are prohibited. So this app is also a minimal OAuth AS (Authlib):

- Discovery: `/.well-known/oauth-authorization-server` (RFC 8414) and `/.well-known/oauth-protected-resource` (RFC 9728, pointing at `/mcp`).
- `POST /oauth/register` — open DCR (RFC 7591), redirect URIs restricted to `https://` (plus `http://localhost` for local).
- `GET /oauth/authorize` — requires a web session (redirects to Google login and back if absent), renders the consent page (server-rendered by FastAPI, not Nuxt), issues a short-lived code bound to PKCE S256. The page is one card carrying its own styles, mark and icon links inline: it may open in a stripped-down connector webview, so it makes no external request and cannot half-load while asking for account access. Its palette is a narrowed copy of the web app's tokens ([web.md](./web.md)) — duplicated deliberately, since FastAPI cannot import the Nuxt stylesheet and consent must not depend on the web app being up. English only for now; it is the one user-facing surface outside the i18n catalog.
- `POST /oauth/token` — code + PKCE → access token (opaque random, stored hashed, 1 h) + refresh token (30 d, rotating). Access tokens authenticate `/mcp` and `/v1/*` exactly like an API key, resolved to the same user.

Result: adding the connector in Claude is "paste URL → Google login → consent" — no manual key copying.

Implementation notes (as built):

- **Public clients only.** DCR issues no client secret and `token_endpoint_auth_method` is `none`; PKCE S256 is the only client authentication, which is what Claude does anyway and leaves no shared secret to leak. One scope, `parse`. Authlib supplies the PKCE primitives; its Flask/Django authorization-server framework is sync, so the endpoints themselves are plain FastAPI routes over `oauth_grants`.
- **Error shapes.** `/oauth/register` and `/oauth/token` answer in RFC form (`{"error": "...", "error_description": "..."}`) because OAuth clients parse that; the app's own error envelope stays on `/v1` and `/api`. `/oauth/authorize` answers a browser, so it renders HTML or redirects.
- **Codes** live 5 min, are single use, and are bound to client, user, PKCE challenge and the redirect URI they were issued for (`oauth_grants.redirect_uri`). A refused client or redirect URI never redirects — it renders an error page.
- **Consent CSRF**: the consent form carries a one-time token stored in the short-lived signed cookie; a cross-site form post cannot produce it. That same cookie parks the authorize request while the user signs in with Google, and only a path under `/oauth/authorize` is resumed.
- **Local without Google**: `/oauth/authorize` answers 401 with a page telling the operator to sign in through the web app's dev login first, instead of redirecting to a Google client that does not exist.
- **`resource` (RFC 8707)** is accepted and ignored: this AS protects exactly one resource, `APP_URL + /mcp`.

## 5. Upload tickets — single-use, job-scoped (the MCP `parse` tool)

A ticket lets an agent do exactly one upload and then read the job that upload created — nothing else. Minted only by the MCP `parse` tool ([mcp.md](./mcp.md)); the point is that an OAuth-connector agent never holds a durable credential, and a leaked ticket is worth one upload to one account for an hour, not an API key.

- Format `srt_<32 random url-safe chars>`; stored as SHA-256 hash + display prefix (`srt_...abc4`) in `upload_tickets` ([database.md](./database.md)). Returned in the tool result exactly once.
- Lifetime `UPLOAD_TICKET_TTL_SECONDS` (default 3600). One TTL covers the upload and the reads; recovery from an expired ticket is minting a new one and re-uploading — dedup makes that free ([jobs.md](./jobs.md) § Dedup).
- **Scope.** An unspent ticket authenticates `POST /v1/parse` once. When the upload creates a job (or hits the dedup cache), the ticket binds to that `job_id` and is marked spent; from then on it authenticates only `GET /v1/jobs/{id}`, `/result`, `/events` for that one job. A request that fails before a job exists (413, 400, 429) does **not** spend the ticket. Every other endpoint — `/mcp` included — refuses `srt_` tokens.
- **Rejection copy is part of the contract.** A spent/expired/unknown ticket gets 401 with: `Upload ticket expired or already spent — call the parse tool again for a fresh ticket; re-uploading the same file returns the cached result instantly.` That message is the agent's only recovery hint, so it lives in the response, not just here.
- **Mint rate limit:** `UPLOAD_TICKET_RATE_PER_HOUR` (default 30) per user; exceeding it is a 429-shaped tool error. Minting also deletes that user's expired tickets (opportunistic cleanup — no sweeper involvement, the table stays small because every mint tidies up).
- Never in query strings, like every other bearer.

## Logging rule

Log key **ids/prefixes** and auth outcomes, never credential material — no session tokens, no API keys, no OpenRouter keys, no OAuth codes/tokens, in logs or exceptions.
