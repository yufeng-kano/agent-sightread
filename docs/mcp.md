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
