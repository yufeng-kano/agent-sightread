# Auth

Four credential kinds, strictly separated. No password login anywhere.

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
- `GET /oauth/authorize` — requires a web session (redirects to Google login and back if absent), renders a minimal consent page (server-rendered by FastAPI, not Nuxt), issues a short-lived code bound to PKCE S256.
- `POST /oauth/token` — code + PKCE → access token (opaque random, stored hashed, 1 h) + refresh token (30 d, rotating). Access tokens authenticate `/mcp` and `/v1/*` exactly like an API key, resolved to the same user.

Result: adding the connector in Claude is "paste URL → Google login → consent" — no manual key copying.

Implementation notes (as built):

- **Public clients only.** DCR issues no client secret and `token_endpoint_auth_method` is `none`; PKCE S256 is the only client authentication, which is what Claude does anyway and leaves no shared secret to leak. One scope, `parse`. Authlib supplies the PKCE primitives; its Flask/Django authorization-server framework is sync, so the endpoints themselves are plain FastAPI routes over `oauth_grants`.
- **Error shapes.** `/oauth/register` and `/oauth/token` answer in RFC form (`{"error": "...", "error_description": "..."}`) because OAuth clients parse that; the app's own error envelope stays on `/v1` and `/api`. `/oauth/authorize` answers a browser, so it renders HTML or redirects.
- **Codes** live 5 min, are single use, and are bound to client, user, PKCE challenge and the redirect URI they were issued for (`oauth_grants.redirect_uri`). A refused client or redirect URI never redirects — it renders an error page.
- **Consent CSRF**: the consent form carries a one-time token stored in the short-lived signed cookie; a cross-site form post cannot produce it. That same cookie parks the authorize request while the user signs in with Google, and only a path under `/oauth/authorize` is resumed.
- **Local without Google**: `/oauth/authorize` answers 401 with a page telling the operator to sign in through the web app's dev login first, instead of redirecting to a Google client that does not exist.
- **`resource` (RFC 8707)** is accepted and ignored: this AS protects exactly one resource, `APP_URL + /mcp`.

## Logging rule

Log key **ids/prefixes** and auth outcomes, never credential material — no session tokens, no API keys, no OpenRouter keys, no OAuth codes/tokens, in logs or exceptions.
