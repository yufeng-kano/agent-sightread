"""User OpenRouter key: encryption at rest, masking, save-time validation (docs/auth.md § 3).

Every upstream call is stubbed with respx — tests never touch OpenRouter (docs/testing.md).
"""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select

from sightread.auth.crypto import (
    decrypt_openrouter_key,
    encrypt_openrouter_key,
    mask_openrouter_key,
)
from sightread.db.models import OpenRouterKey
from sightread.upstream.openrouter import KEY_URL

from .conftest import CSRF_HEADERS, TEST_SECRET_KEY

CANDIDATE_KEY = "sk-or-v1-0123456789abcdef0123456789abcdef"


def test_encryption_round_trip_uses_a_fresh_nonce() -> None:
    first = encrypt_openrouter_key(TEST_SECRET_KEY, CANDIDATE_KEY)
    second = encrypt_openrouter_key(TEST_SECRET_KEY, CANDIDATE_KEY)

    assert first != second  # random nonce per encryption
    assert CANDIDATE_KEY.encode() not in first
    assert decrypt_openrouter_key(TEST_SECRET_KEY, first) == CANDIDATE_KEY
    assert decrypt_openrouter_key(TEST_SECRET_KEY, second) == CANDIDATE_KEY


def test_a_different_secret_key_cannot_decrypt() -> None:
    blob = encrypt_openrouter_key(TEST_SECRET_KEY, CANDIDATE_KEY)
    with pytest.raises(Exception):  # noqa: B017 - cryptography raises InvalidTag
        decrypt_openrouter_key("another-secret-key", blob)


def test_masking_hides_the_body_of_the_key() -> None:
    masked = mask_openrouter_key(CANDIDATE_KEY)
    assert masked == "sk-or-v1...cdef"
    assert CANDIDATE_KEY not in masked


@respx.mock
async def test_put_validates_upstream_then_stores_ciphertext(
    signed_in: AsyncClient, sessionmaker
) -> None:
    route = respx.get(KEY_URL).mock(
        return_value=httpx.Response(200, json={"data": {"label": "test", "usage": 0}})
    )

    stored = await signed_in.put(
        "/api/openrouter-key", json={"key": CANDIDATE_KEY}, headers=CSRF_HEADERS
    )
    assert stored.status_code == 200
    assert stored.json()["masked"] == "sk-or-v1...cdef"
    assert route.calls.call_count == 1
    assert route.calls.last.request.headers["authorization"] == f"Bearer {CANDIDATE_KEY}"

    async with sessionmaker() as db:
        row = (await db.execute(select(OpenRouterKey))).scalar_one()
    assert CANDIDATE_KEY.encode() not in row.ciphertext
    assert decrypt_openrouter_key(TEST_SECRET_KEY, row.ciphertext) == CANDIDATE_KEY

    fetched = await signed_in.get("/api/openrouter-key")
    assert fetched.json()["present"] is True
    assert fetched.json()["masked"] == "sk-or-v1...cdef"
    assert CANDIDATE_KEY not in fetched.text

    me = await signed_in.get("/api/me")
    assert me.json()["openrouter_key"]["masked"] == "sk-or-v1...cdef"
    assert CANDIDATE_KEY not in me.text


@respx.mock
async def test_put_rejects_an_invalid_key_and_stores_nothing(
    signed_in: AsyncClient, sessionmaker
) -> None:
    respx.get(KEY_URL).mock(return_value=httpx.Response(401, json={"error": "invalid"}))

    response = await signed_in.put(
        "/api/openrouter-key", json={"key": "sk-or-v1-bogus-key-value"}, headers=CSRF_HEADERS
    )
    assert response.status_code == 400
    assert response.json() == {
        "error": {"type": "invalid_request", "message": "OpenRouter rejected this key"}
    }

    async with sessionmaker() as db:
        assert (await db.execute(select(OpenRouterKey))).scalars().all() == []


@respx.mock
async def test_upstream_outage_is_not_reported_as_a_bad_key(signed_in: AsyncClient) -> None:
    respx.get(KEY_URL).mock(return_value=httpx.Response(500, text="boom"))

    response = await signed_in.put(
        "/api/openrouter-key", json={"key": CANDIDATE_KEY}, headers=CSRF_HEADERS
    )
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream"


@respx.mock
async def test_delete_removes_the_key(signed_in: AsyncClient) -> None:
    respx.get(KEY_URL).mock(return_value=httpx.Response(200, json={"data": {}}))
    await signed_in.put("/api/openrouter-key", json={"key": CANDIDATE_KEY}, headers=CSRF_HEADERS)

    removed = await signed_in.delete("/api/openrouter-key", headers=CSRF_HEADERS)
    assert removed.status_code == 204

    fetched = await signed_in.get("/api/openrouter-key")
    assert fetched.json() == {"present": False, "masked": None, "updated_at": None}
