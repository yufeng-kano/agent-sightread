# Parsing pipeline

## PDF engine: Poppler via subprocess — this is a hard rule

All PDF work goes through Poppler CLI tools in short-lived subprocesses:

- `pdfinfo` — page count + page dimensions (points).
- `pdftoppm -png -r <dpi>` — page rendering for vision calls, scaled so the long edge ≤ **2000 px** (large images destabilize VLM detection).

Why subprocess, not a linked library: crash isolation (a malicious PDF kills the child, not the worker), free multi-core parallelism, and licensing (Poppler is GPL — fine to invoke as a separate program; PyMuPDF is AGPL and banned here). Every subprocess gets a timeout (default 60 s/page) and runs against the job's temp directory only.

## Vision-only conversion

Every page is converted the same way — **one path, no routing**:

1. Render the page (`pdftoppm`).
2. Send the rendered image to the user's chosen model via OpenRouter with the transcription prompt. The model returns the page's markdown with figure placeholders inline. `method: "vision"` on every page.

There is no PDF-text-layer conversion path: the product converts what the page *looks like*, and a single pipeline means every page obeys the same prompt, the same figure contract and the same failure rules. The PDF text layer is never extracted — `pdfinfo` and `pdftoppm` are the only Poppler calls.

A page that cannot be rendered or transcribed → entry in `errors`, parsing continues. Whole document unreadable → job fails, no partial markdown; the failure message names the per-page reasons.

## Page markers

The assembled markdown carries one marker line per page, immediately before that page's content:

```markdown
<!-- page: 4 -->
```

Markers are how a caller maps any passage back to its page (citations, cross-checking figures). They are HTML comments, so ordinary markdown renderers hide them.

## Coordinate contract

- Figures: `bbox` = `[ymin, xmin, ymax, xmax]`, normalized 0–1000, origin top-left (`yxyx_norm1000`, Gemini-native — prompt the model for this format explicitly).
- The service **never converts coordinates**; the response declares `meta.bbox_format` and the receiver does the one and only conversion at crop time.
- Placeholder: `![fig{n}](sightread://p{page}/{ymin},{xmin},{ymax},{xmax})`, caption verbatim on the next line.
- Figure ids are document-wide (`fig1`, `fig2`, …) and the page number is **ours**, not the model's: the model emits the placeholder in place and the assembler renumbers it. Boxes are clamped to 0–1000; a box that is still degenerate (zero or negative area) is dropped, never guessed at.

## Prompts

The transcription prompt is a template with two tokens, `{page}` and `{bbox_format}`, substituted per call (plain string replacement — a template with stray braces must not break a job).

Resolution order for a job's prompt, decided at enqueue time and stored on the job row:

1. **The user's custom system prompt** (`user_settings.system_prompt`, set on the web settings page) when one is stored. It replaces the template entirely — including for preset profiles — and figure/bbox quality is then the user's own responsibility.
2. The preset profile's template, for a job running a profile.
3. `DEFAULT_PROMPT_TEMPLATE` (shipped in code, shown on the settings page as the default).

`jobs.prompt` holds the effective template verbatim (reproducibility); `jobs.prompt_sha256` is part of the dedup cache key ([jobs.md](./jobs.md)), so editing a custom prompt invalidates cached results parsed with the old one.

## Profiles

A profile = model id + prompt template + response parser + `bbox_format` + profile version. Presets ship in code (`gemini-yxyx` targeting current Gemini flash-tier vision models, `qwen-yxyx` targeting current Qwen VL models; both prompt the same `yxyx_norm1000` contract — resolve actual ids from the live `/v1/models` catalog at startup, never hard-code a dead id). Users may instead pick **any** image-input model: it runs with the default prompt template, is labeled untested, and bbox quality is explicitly their responsibility. Such a job stores `profile: null` and `profile_version: 0`, so a change to the default template is covered by `PIPELINE_VERSION` instead.

`profile_version` and global `PIPELINE_VERSION` are part of the dedup cache key ([jobs.md](./jobs.md)) so prompt/pipeline improvements invalidate old cached results.

## Image input

Accepted: jpg, png, webp, heic. Normalization before the vision call, in this order:

1. HEIC → JPEG (pillow-heif).
2. Apply EXIF orientation.
3. Downscale to long edge ≤ 2000 px.

Single page; `width_pt`/`height_pt` are the pixel dimensions of the (original) input image; bbox space is still 0–1000 normalized.

## OpenRouter usage

- One request per page, fanned out with an asyncio semaphore (`VISION_CONCURRENCY_PER_JOB`, default 8); 429 from OpenRouter → exponential backoff + reduced concurrency for that job.
- Every response's `usage` object (tokens + actual `cost` — always included by OpenRouter) is written to `usage_log` per call. Never maintain a local price table.
- 402 → mark the page failed with reason `payment`, continue remaining pages only if the error is page-scoped; abort the job when the key is clearly dead.
