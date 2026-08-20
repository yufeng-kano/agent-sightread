"""OpenRouter client — the only module that talks to OpenRouter and the only one that
ever holds a decrypted user key (docs/project-structure.md).

Key material is never logged and never appears in raised messages.
"""

from __future__ import annotations

import time

import httpx

from ..errors import ApiError

BASE_URL = "https://openrouter.ai/api/v1"
MODELS_URL = f"{BASE_URL}/models"
KEY_URL = f"{BASE_URL}/key"

MODELS_CACHE_TTL_SECONDS = 3600
REQUEST_TIMEOUT_SECONDS = 20.0

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
