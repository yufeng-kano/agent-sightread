"""`GET /v1/models` and `GET /v1/profiles` (docs/api.md, docs/parsing.md § Profiles).

The catalog is a respx fixture — the real OpenRouter endpoint is never called.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import AsyncClient

from sightread.parsing.profiles import get_profile
from sightread.upstream.openrouter import MODELS_URL, reset_models_cache

CATALOG = {
    "data": [
        {
            "id": "google/gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "created": 1_750_000_000,
            "context_length": 1_048_576,
            "pricing": {"prompt": "0.0000003", "completion": "0.0000025"},
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            "id": "google/gemini-2.0-flash-001",
            "name": "Gemini 2.0 Flash",
            "created": 1_740_000_000,
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            "id": "google/gemini-2.5-flash-lite",
            "name": "Gemini 2.5 Flash Lite",
            "created": 1_755_000_000,
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            # A newer routing variant of a newer base model: offline batch inference,
            # which a profile must never resolve to.
            "id": "google/gemini-3.7-flash:batch",
            "name": "Gemini 3.7 Flash (batch)",
            "created": 1_760_000_000,
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            "id": "anthropic/claude-vision",
            "name": "Claude Vision",
            "created": 1_745_000_000,
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            "id": "openai/text-only",
            "name": "Text Only",
            "created": 1_748_000_000,
            "architecture": {"input_modalities": ["text"]},
        },
        {
            "id": "vendor/no-architecture",
            "name": "Malformed Entry",
            "created": 1_749_000_000,
        },
    ]
}


@pytest.fixture(autouse=True)
def clear_catalog_cache():
    reset_models_cache()
    yield
    reset_models_cache()


@respx.mock
async def test_models_are_filtered_to_image_input(signed_in: AsyncClient) -> None:
    respx.get(MODELS_URL).mock(return_value=httpx.Response(200, json=CATALOG))

    response = await signed_in.get("/v1/models")
    assert response.status_code == 200
    models = response.json()["data"]

    assert [model["id"] for model in models] == [
        "google/gemini-2.5-flash",
        "google/gemini-2.0-flash-001",
        "google/gemini-2.5-flash-lite",
        "google/gemini-3.7-flash:batch",
        "anthropic/claude-vision",
    ]
    # The catalog still lists every image-input model, variants included; only the base
    # id a preset resolves to is flagged.
    recommended = [model["id"] for model in models if model["recommended"]]
    assert recommended == ["google/gemini-2.5-flash"]


@respx.mock
async def test_catalog_is_cached_in_process(signed_in: AsyncClient) -> None:
    route = respx.get(MODELS_URL).mock(return_value=httpx.Response(200, json=CATALOG))

    await signed_in.get("/v1/models")
    await signed_in.get("/v1/models")
    await signed_in.get("/v1/profiles")

    assert route.calls.call_count == 1


@respx.mock
async def test_profiles_resolve_a_live_model(signed_in: AsyncClient) -> None:
    respx.get(MODELS_URL).mock(return_value=httpx.Response(200, json=CATALOG))

    response = await signed_in.get("/v1/profiles")
    assert response.status_code == 200
    profile = response.json()["data"][0]
    assert profile["id"] == "gemini-yxyx"
    assert profile["model"] == "google/gemini-2.5-flash"
    assert profile["bbox_format"] == "yxyx_norm1000"
    assert profile["available"] is True


def test_profile_never_resolves_to_a_variant_suffix() -> None:
    """`:batch` is offline inference and `:free`/`:nitro` are routing variants: a preset
    resolves to the base id even when a variant is newer."""
    profile = get_profile("gemini-yxyx")
    assert profile is not None
    catalog = [
        {"id": "google/gemini-x-flash:batch", "created": 1_760_000_000},
        {"id": "google/gemini-x-flash", "created": 1_750_000_000},
        {"id": "google/gemini-x-flash:free", "created": 1_759_000_000},
        {"id": "google/gemini-x-flash:extended", "created": 1_758_000_000},
        {"id": "google/gemini-x-flash:nitro", "created": 1_757_000_000},
    ]

    assert profile.resolve_model(catalog) == "google/gemini-x-flash"
    # A catalog offering nothing but variants offers this profile no model at all.
    assert profile.resolve_model([entry for entry in catalog if ":" in entry["id"]]) is None


def test_profile_reports_unavailable_when_the_catalog_has_no_match() -> None:
    profile = get_profile("gemini-yxyx")
    assert profile is not None
    assert profile.resolve_model([{"id": "anthropic/claude-vision", "created": 1}]) is None
    assert profile.resolve_model([]) is None


@respx.mock
async def test_upstream_failure_surfaces_as_an_upstream_error(signed_in: AsyncClient) -> None:
    respx.get(MODELS_URL).mock(side_effect=httpx.ConnectError("no route"))

    response = await signed_in.get("/v1/models")
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream"


async def test_catalog_reads_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/v1/models")
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "auth"
