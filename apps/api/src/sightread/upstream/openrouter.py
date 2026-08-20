"""OpenRouter client — the only module that talks to OpenRouter and the only one that
ever holds a decrypted user key (docs/project-structure.md).

Key material is never logged and never appears in raised messages.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.crypto import decrypt_openrouter_key
from ..db.models import OpenRouterKey
from ..errors import ApiError
from ..parsing.markdown import FigureBox, clean_bbox

BASE_URL = "https://openrouter.ai/api/v1"
MODELS_URL = f"{BASE_URL}/models"
KEY_URL = f"{BASE_URL}/key"
CHAT_URL = f"{BASE_URL}/chat/completions"

MODELS_CACHE_TTL_SECONDS = 3600
REQUEST_TIMEOUT_SECONDS = 20.0
# A page of dense text can take a vision model a while; this is the whole-request ceiling.
CHAT_TIMEOUT_SECONDS = 180.0

DATA_URL_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

# Model answers sometimes arrive wrapped in a fence despite the prompt.
_CODE_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")

# In-process catalog cache: (fetched_at, models). One hour per docs/api.md § GET /v1/models.
_models_cache: tuple[float, list[dict]] | None = None


def reset_models_cache() -> None:
    global _models_cache
    _models_cache = None


async def validate_api_key(candidate: str) -> bool:
    """Check a user-supplied OpenRouter key before storing it (docs/auth.md § 3).

    Returns False for a rejected key; raises `ApiError(upstream)` when OpenRouter itself
    is unhealthy, so a provider outage is never reported as a bad key.
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(KEY_URL, headers={"Authorization": f"Bearer {candidate}"})
    except httpx.HTTPError as exc:
        raise ApiError(502, "upstream", "Could not reach OpenRouter to validate the key") from exc
    if response.status_code == 200:
        return True
    if response.status_code in (401, 403):
        return False
    raise ApiError(502, "upstream", f"OpenRouter returned {response.status_code} for key check")


async def fetch_image_models(now: float | None = None) -> list[dict]:
    """The model catalog filtered to image-input models, cached in process for an hour.

    The upstream catalog endpoint needs no credentials, so this never touches a user key.
    """
    global _models_cache
    now = time.monotonic() if now is None else now
    if _models_cache is not None and now - _models_cache[0] < MODELS_CACHE_TTL_SECONDS:
        return _models_cache[1]

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(MODELS_URL)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise ApiError(502, "upstream", "Could not reach the OpenRouter model catalog") from exc

    models = [
        model
        for model in payload.get("data", [])
        if "image" in (model.get("architecture") or {}).get("input_modalities", [])
    ]
    _models_cache = (now, models)
    return models


# --- vision calls ---------------------------------------------------------------------


class UpstreamError(Exception):
    """An OpenRouter call failed. `fatal` marks a failure that will repeat for every page,
    so the caller should abort the whole job instead of burning pages on it."""

    def __init__(self, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal


class RateLimited(UpstreamError):
    """429. The caller backs off and reduces that job's concurrency (docs/parsing.md)."""

    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("OpenRouter rate-limited this key")
        self.retry_after = retry_after


class PaymentRequired(UpstreamError):
    """402. The page fails with reason `payment`; a repeat means the key is dead."""

    def __init__(self) -> None:
        super().__init__("OpenRouter reported exhausted credits")


@dataclass(frozen=True)
class UserKey:
    """A user's OpenRouter key, still encrypted. Only this module ever opens it, and the
    plaintext never leaves the request it authorises (docs/project-structure.md)."""

    ciphertext: bytes
    secret_key: str

    def __repr__(self) -> str:  # never let key material reach a log line
        return "UserKey(...)"

    def authorization(self) -> str:
        return f"Bearer {decrypt_openrouter_key(self.secret_key, self.ciphertext)}"


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cost: Decimal


@dataclass(frozen=True)
class PageTranscription:
    markdown: str
    usage: Usage


@dataclass(frozen=True)
class FigureDetection:
    figures: list[FigureBox]
    # Detections the model returned in an unusable shape; reported, never guessed at.
    dropped: int
    usage: Usage


async def load_user_key(db: AsyncSession, secret_key: str, user_id: int) -> UserKey | None:
    row = (
        await db.execute(select(OpenRouterKey).where(OpenRouterKey.user_id == user_id))
    ).scalar_one_or_none()
    return None if row is None else UserKey(ciphertext=row.ciphertext, secret_key=secret_key)


def image_data_url(path: Path) -> str:
    media_type = DATA_URL_MEDIA_TYPES.get(path.suffix.lower(), "image/png")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _usage(payload: dict) -> Usage:
    """OpenRouter always returns `usage`; cost is the real amount billed to the user."""
    raw = payload.get("usage") or {}
    try:
        cost = Decimal(str(raw.get("cost", "0"))).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError):
        cost = Decimal("0")
    return Usage(
        prompt_tokens=_int(raw.get("prompt_tokens")),
        completion_tokens=_int(raw.get("completion_tokens")),
        cost=cost,
    )


def _message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise UpstreamError("OpenRouter returned no completion")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Some providers answer with content parts instead of a plain string.
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    raise UpstreamError("OpenRouter returned an unreadable completion")


def _raise_for_error_payload(payload: dict) -> None:
    """OpenRouter can report a provider failure inside a 200 response."""
    error = payload.get("error")
    if not isinstance(error, dict):
        return
    code = _int(error.get("code"))
    if code == 402:
        raise PaymentRequired()
    if code == 429:
        raise RateLimited()
    raise UpstreamError(f"OpenRouter reported an upstream error ({code or 'unknown'})")


async def _chat_with_image(key: UserKey, model: str, prompt: str, image: Path) -> tuple[str, Usage]:
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url(image)}},
                ],
            }
        ],
        # Ask for token counts and the actual cost; never price locally (docs/parsing.md).
        "usage": {"include": True},
    }
    try:
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                CHAT_URL, headers={"Authorization": key.authorization()}, json=body
            )
    except httpx.HTTPError as exc:
        raise UpstreamError("OpenRouter was unreachable") from exc

    if response.status_code == 429:
        retry_after = response.headers.get("retry-after")
        raise RateLimited(float(retry_after) if (retry_after or "").isdigit() else None)
    if response.status_code == 402:
        raise PaymentRequired()
    if response.status_code in (401, 403):
        raise UpstreamError("OpenRouter rejected the stored key", fatal=True)
    if response.status_code >= 400:
        raise UpstreamError(f"OpenRouter returned {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamError("OpenRouter returned a non-JSON body") from exc
    _raise_for_error_payload(payload)
    return _message_text(payload), _usage(payload)


async def transcribe_page(
    key: UserKey,
    model: str,
    prompt_template: str,
    bbox_format: str,
    image: Path,
    page_no: int,
) -> PageTranscription:
    """Transcribe one rendered page; the answer carries its own figure placeholders."""
    prompt = prompt_template.format(page=page_no, bbox_format=bbox_format)
    text, usage = await _chat_with_image(key, model, prompt, image)
    return PageTranscription(markdown=_CODE_FENCE_RE.sub("", text.strip()), usage=usage)


async def detect_figures(
    key: UserKey,
    model: str,
    prompt_template: str,
    bbox_format: str,
    image: Path,
) -> FigureDetection:
    """Figure boxes for a page whose text came from the PDF text layer."""
    prompt = prompt_template.format(bbox_format=bbox_format)
    text, usage = await _chat_with_image(key, model, prompt, image)

    stripped = _CODE_FENCE_RE.sub("", text.strip())
    start, end = stripped.find("["), stripped.rfind("]")
    if start < 0 or end <= start:
        # A model that answers in prose has told us nothing usable, but nothing wrong.
        return FigureDetection(figures=[], dropped=0, usage=usage)
    try:
        items = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return FigureDetection(figures=[], dropped=1, usage=usage)

    figures: list[FigureBox] = []
    dropped = 0
    for item in items if isinstance(items, list) else []:
        raw = item.get("bbox") if isinstance(item, dict) else None
        if not isinstance(raw, list) or len(raw) != 4:
            dropped += 1
            continue
        try:
            bbox = clean_bbox(tuple(int(value) for value in raw))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            bbox = None
        if bbox is None:
            dropped += 1
            continue
        caption = item.get("caption")
        figures.append(
            FigureBox(bbox=bbox, caption=caption.strip() if isinstance(caption, str) else "")
        )
    return FigureDetection(figures=figures, dropped=dropped, usage=usage)
