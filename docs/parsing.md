# Parsing pipeline

## PDF engine: Poppler via subprocess — this is a hard rule

All PDF work goes through Poppler CLI tools in short-lived subprocesses:

- `pdfinfo` — page count + page dimensions (points).
- `pdftotext -bbox` (per page) — text layer with word boxes, used for routing and text_layer conversion.
- `pdftoppm -png -r <dpi>` — page rendering for vision calls, scaled so the long edge ≤ **2000 px** (large images destabilize VLM detection).

Why subprocess, not a linked library: crash isolation (a malicious PDF kills the child, not the worker), free multi-core parallelism, and licensing (Poppler is GPL — fine to invoke as a separate program; PyMuPDF is AGPL and banned here). Every subprocess gets a timeout (default 60 s/page) and runs against the job's temp directory only.

## Per-page routing

1. Extract text layer (`pdftotext -bbox`).
2. **text_layer path** — page has a real text layer and simple single-column layout (heuristic: word count above threshold, no multi-column x-clustering, low math/table density): convert directly, `method: "text_layer"`. No LLM call, costs nothing.
3. **vision path** — everything else (scanned, two-column, table/math heavy): render page, send to the user's chosen model via OpenRouter, `method: "vision"`.
4. **Figure bbox detection always runs via vision** on the rendered page, regardless of path.

Unreadable page → entry in `errors`, parsing continues. Whole document unreadable → job fails, no partial markdown.

## Coordinate contract

- Figures: `bbox` = `[ymin, xmin, ymax, xmax]`, normalized 0–1000, origin top-left (`yxyx_norm1000`, Gemini-native — prompt the model for this format explicitly).
- The service **never converts coordinates**; the response declares `meta.bbox_format` and the receiver does the one and only conversion at crop time.
- Placeholder: `![fig{n}](sightread://p{page}/{ymin},{xmin},{ymax},{xmax})`, caption verbatim on the next line.
- Figure ids are document-wide (`fig1`, `fig2`, …) and the page number is **ours**, not the model's. On a vision page the model emits the placeholder in place; on a text-layer page the boxes come from a separate detection call and are appended at the end of that page's markdown, in the order the model returned them. Boxes are clamped to 0–1000; a box that is still degenerate (zero or negative area) is dropped, never guessed at.

## Profiles

A profile = model id + coordinate prompt template + response parser + `bbox_format` + profile version. Presets ship in code (`gemini-yxyx` targeting current Gemini flash-tier vision models, `qwen-yxyx` targeting current Qwen VL models; both prompt the same `yxyx_norm1000` contract — resolve actual ids from the live `/v1/models` catalog at startup, never hard-code a dead id). Users may instead pick **any** image-input model: it runs with the default prompt template, is labeled untested, and bbox quality is explicitly their responsibility. Such a job stores `profile: null` and `profile_version: 0`, so a change to the default templates is covered by `PIPELINE_VERSION` instead.

`profile_version` and global `PIPELINE_VERSION` are part of the dedup cache key ([jobs.md](./jobs.md)) so prompt/pipeline improvements invalidate old cached results.

## Image input (parse_image path)

Accepted: jpg, png, webp, heic. Normalization before the vision call, in this order:

1. HEIC → JPEG (pillow-heif).
2. Apply EXIF orientation.
3. Downscale to long edge ≤ 2000 px.

Single page; `width_pt`/`height_pt` are the pixel dimensions of the (original) input image; bbox space is still 0–1000 normalized.

## OpenRouter usage

- One request per vision page, fanned out with an asyncio semaphore (`VISION_CONCURRENCY_PER_JOB`, default 8); 429 from OpenRouter → exponential backoff + reduced concurrency for that job.
- Every response's `usage` object (tokens + actual `cost` — always included by OpenRouter) is written to `usage_log` per call. Never maintain a local price table.
- 402 → mark the page failed with reason `payment`, continue remaining pages only if the error is page-scoped; abort the job when the key is clearly dead.
