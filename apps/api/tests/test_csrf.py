"""CSRF pairing on the cookie-authenticated control plane (docs/api.md).

SameSite=Lax stops cross-site form posts from carrying the cookie; the custom header is
the second half of the pair, since a cross-origin form cannot set one.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from .conftest import CSRF_HEADERS

MUTATIONS = [
    ("post", "/api/keys", {"name": "x"}),
    ("delete", "/api/keys/1", None),
    ("put", "/api/openrouter-key", {"key": "sk-or-v1-something"}),
    ("delete", "/api/openrouter-key", None),
    ("put", "/api/settings", {"default_model": None, "default_profile": None}),
    ("post", "/api/auth/logout", None),
    ("post", "/api/auth/dev-login", None),
]


@pytest.mark.parametrize(("method", "path", "body"), MUTATIONS)
async def test_mutations_require_the_custom_header(
    signed_in: AsyncClient, method: str, path: str, body: dict | None
) -> None:
    response = await signed_in.request(method, path, json=body)
    assert response.status_code == 403
    assert response.json() == {
        "error": {"type": "auth", "message": "Missing X-Requested-With header"}
    }


async def test_reads_do_not_require_the_custom_header(signed_in: AsyncClient) -> None:
    assert (await signed_in.get("/api/me")).status_code == 200
    assert (await signed_in.get("/api/keys")).status_code == 200
    assert (await signed_in.get("/api/jobs")).status_code == 200


async def test_settings_accept_a_known_profile_only(signed_in: AsyncClient) -> None:
    ok = await signed_in.put(
        "/api/settings",
        json={"default_model": "google/gemini-2.5-flash", "default_profile": "gemini-yxyx"},
        headers=CSRF_HEADERS,
    )
    assert ok.status_code == 200
    assert ok.json() == {
        "default_model": "google/gemini-2.5-flash",
        "default_profile": "gemini-yxyx",
        "system_prompt": None,
    }

    bad = await signed_in.put(
        "/api/settings", json={"default_profile": "does-not-exist"}, headers=CSRF_HEADERS
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["type"] == "invalid_request"
