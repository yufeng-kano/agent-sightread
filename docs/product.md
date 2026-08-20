# Product

## What it is

agent-sightread is a hosted, multi-user document-understanding service: PDF and image in, markdown with figure coordinate placeholders out. It descends from the "sightread MCP" spec (vision-based extraction, coordinates-not-crops) but is deliberately a **platform**, not a stateless tool.

## Deliberate deviations from the origin spec

The origin spec (v0.1) is a reference, not a contract. Decisions that supersede it:

1. **Not stateless.** Jobs, results, and usage live in PostgreSQL. Parse results (markdown + metadata) are kept indefinitely; **source files are deleted immediately** when a job reaches a terminal state (see [jobs.md](./jobs.md)).
2. **REST is the core; MCP is a thin shell** over the same service layer ([mcp.md](./mcp.md)).
3. **No `file path` source.** Hosted service accepts uploads (multipart) or base64 only — server paths would be an LFI.
4. **Model is user-chosen.** Users pick any image-input model from OpenRouter; preset **profiles** bundle tested model + coordinate prompt + parser. Off-profile models are allowed and flagged untested — bbox quality is the user's responsibility ([parsing.md](./parsing.md)).
5. **bbox format is declared per response** (`bbox_format` field), not assumed globally.
6. **No server-side cropping.** The service parses and returns; cropping is the receiver's job. The response carries everything needed (page dims, bbox format, method, model).
7. **Poppler, not PyMuPDF.** PyMuPDF is AGPL; Poppler is used via subprocess (crash isolation for free). This repo is MIT-licensed open source.

## Tenants and trust model

- Every user brings their **own OpenRouter key**; vision spend is theirs. The operator pays only for CPU/disk, protected by per-user concurrency caps.
- Documents are untrusted input: parsing runs in short-lived subprocesses with timeouts; uploads are size- and page-capped.
- Document content is sensitive: source files are short-lived, prompts/completions are never logged, results are visible only to their owner.

## Non-goals

- No password auth. No staging environment. No multi-server orchestration.
- No built-in OCR models or self-hosted VLMs — OpenRouter is the only inference path.
- No cross-user dedup cache (per-user only; global sharing would leak parse history and spend).
