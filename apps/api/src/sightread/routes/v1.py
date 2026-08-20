"""Data plane `/v1/*` (docs/api.md).

Phase 1 ships the catalog reads. `POST /v1/parse` and the job/SSE endpoints arrive with
the parsing pipeline and job runner.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..auth.deps import ApiKeyUser, ReaderUser
from ..errors import ApiError
from ..parsing.profiles import PRESET_PROFILES
from ..upstream.openrouter import fetch_image_models

router = APIRouter(prefix="/v1", tags=["data"])


@router.get("/models")
async def list_models(user: ReaderUser):
    """Image-input models from the live OpenRouter catalog, cached in process for ~1 h.

    `recommended` marks the models the preset profiles currently resolve to.
    """
    catalog = await fetch_image_models()
    recommended = {
        model_id
        for model_id in (profile.resolve_model(catalog) for profile in PRESET_PROFILES)
        if model_id
    }
    return {
        "data": [
            {
                "id": model["id"],
                "name": model.get("name"),
                "context_length": model.get("context_length"),
                "pricing": model.get("pricing"),
                "recommended": model["id"] in recommended,
            }
            for model in catalog
        ]
    }


@router.get("/profiles")
async def list_profiles(user: ReaderUser):
    """Preset profiles with the model each currently resolves to from the live catalog."""
    catalog = await fetch_image_models()
    profiles = []
    for profile in PRESET_PROFILES:
        model_id = profile.resolve_model(catalog)
        profiles.append(
            {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description,
                "model": model_id,
                "bbox_format": profile.bbox_format,
                "profile_version": profile.profile_version,
                "available": model_id is not None,
            }
        )
    return {"data": profiles}


@router.post("/parse")
async def parse(user: ApiKeyUser):
    raise ApiError(501, "internal", "Parsing is not enabled on this deployment yet")
