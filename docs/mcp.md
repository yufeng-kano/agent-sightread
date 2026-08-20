# MCP server

A **thin shell over the REST service layer** — no parsing logic of its own, no separate auth store. If MCP-the-spec changes, only this shell changes.

## Transport & auth

- Endpoint: `POST /mcp` (streamable HTTP, official `mcp` Python SDK, mounted inside the same FastAPI app).
- Auth: `Authorization: Bearer` with either an OAuth access token (Claude Connectors path — see [auth.md](./auth.md) § 4) or a project API key (scripts/self-hosted agents). Both resolve to a user; the user's stored OpenRouter key and defaults apply.
- Never accept tokens in query strings.

## Tools

### parse_document

Input: `{ source: <base64>, media_type: "application/pdf", pages?: "1-5,8", model?, profile?, force? }`
No file-path source — hosted service, uploads only ([product.md](./product.md)).

Behavior: creates the same job as `POST /v1/parse` (dedup applies), reports MCP progress notifications as pages finish, returns the full result payload of `GET /v1/jobs/{id}/result`. Long documents: keep streaming progress; if the client disconnects, the job keeps running and `get_result` can fetch it later.

### parse_image

Same, `media_type: image/*` (jpg/png/webp/heic), single page.

### get_result

`{ job_id }` → status, or the full result when terminal. Lets a client recover from disconnects.

## Claude Connectors flow (the reason the OAuth AS exists)

1. User adds `https://<host>/mcp` as a custom connector.
2. Claude discovers `/.well-known/oauth-protected-resource` → AS metadata → performs Dynamic Client Registration → browser consent (Google session) → token.
3. Tool calls arrive with the OAuth bearer; usage lands in the same `usage_log` as REST calls.

Keep tool descriptions short and explicit about the coordinate contract (`bbox_format`, `sightread://` placeholders, "you crop, we don't").

## Implementation notes (as built)

- **Stateless streamable HTTP.** Every request carries its own bearer and gets its own transport, so a connector never depends on session affinity and a token can never be inherited from an earlier session. The SDK's session manager runs for the app's lifetime (FastAPI lifespan).
- **Auth is ours, not the SDK's.** A small ASGI guard in front of the transport resolves the bearer through the same code path as `/v1` and answers 401 with `WWW-Authenticate: Bearer resource_metadata="<APP_URL>/.well-known/oauth-protected-resource"` — the pointer that starts a connector's OAuth discovery (RFC 9728).
- **`parse_document` / `parse_image`** take `source` (base64), `media_type`, and the same optional `model` / `profile` / `pages` / `force` as `POST /v1/parse`; they run `jobs.intake`, report MCP progress from `jobs.events`, and return the `GET /v1/jobs/{id}/result` payload (a dedup hit returns it immediately with `meta.cached: true`). A `source` that looks like a filesystem path is refused by name.
- **`get_result`** returns `{job_id, status, page_count, pages_done, error, result}` — `result` is null until the job is terminal.
