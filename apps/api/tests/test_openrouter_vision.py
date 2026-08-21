"""Vision calls against a stubbed OpenRouter. No test ever reaches the network.

The stubs assert on the request we send (image data URL, usage flag) and on how defensively
we read what comes back (docs/testing.md § Cost safety).
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx

from sightread.auth.crypto import encrypt_openrouter_key
from sightread.upstream.openrouter import (
    CHAT_URL,
    PaymentRequired,
    RateLimited,
    UpstreamError,
    UserKey,
    transcribe_page,
)

SECRET = "test-secret-key-not-a-real-one"
PROMPT = "Transcribe page {page} in {bbox_format}."


@pytest.fixture
def key() -> UserKey:
    return UserKey(ciphertext=encrypt_openrouter_key(SECRET, "sk-or-v1-test"), secret_key=SECRET)


def completion(content: str, cost: str = "0.000420") -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": 1200,
            "completion_tokens": 300,
            "total_tokens": 1500,
            "cost": cost,
        },
    }


@respx.mock
async def test_transcribe_page_sends_the_image_and_records_usage(key, documents) -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion("# Page\n\ntext"))
    )

    result = await transcribe_page(
        key, "vendor/model", PROMPT, "yxyx_norm1000", documents["png"], 7
    )

    assert result.markdown == "# Page\n\ntext"
    assert result.usage.prompt_tokens == 1200
    assert result.usage.cost == Decimal("0.000420")

    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "vendor/model"
    assert sent["usage"] == {"include": True}
    parts = sent["messages"][0]["content"]
    assert parts[0]["text"] == "Transcribe page 7 in yxyx_norm1000."
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    # The decrypted key only ever appears in the Authorization header.
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-or-v1-test"


@respx.mock
async def test_transcribe_page_strips_a_code_fence(key, documents) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=completion("```markdown\n# Page\n```"))
    )
    result = await transcribe_page(key, "m", PROMPT, "yxyx_norm1000", documents["png"], 1)
    assert result.markdown == "# Page"


@respx.mock
async def test_a_prompt_with_stray_braces_still_substitutes_its_tokens(key, documents) -> None:
    """User-supplied templates go through plain replacement, never `str.format`."""
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=completion("ok")))

    await transcribe_page(
        key, "m", "Emit {json} like {\"a\": 1} for page {page}.", "yxyx_norm1000",
        documents["png"], 3,
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["messages"][0]["content"][0]["text"] == 'Emit {json} like {"a": 1} for page 3.'


@respx.mock
async def test_rate_limit_carries_retry_after(key, documents) -> None:
    respx.post(CHAT_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "12"}))

    with pytest.raises(RateLimited) as raised:
        await transcribe_page(key, "m", PROMPT, "yxyx_norm1000", documents["png"], 1)
    assert raised.value.retry_after == 12


@respx.mock
async def test_payment_required(key, documents) -> None:
    respx.post(CHAT_URL).mock(return_value=httpx.Response(402, json={"error": {"code": 402}}))

    with pytest.raises(PaymentRequired):
        await transcribe_page(key, "m", PROMPT, "yxyx_norm1000", documents["png"], 1)


@respx.mock
async def test_a_rejected_key_is_fatal(key, documents) -> None:
    respx.post(CHAT_URL).mock(return_value=httpx.Response(401))

    with pytest.raises(UpstreamError) as raised:
        await transcribe_page(key, "m", PROMPT, "yxyx_norm1000", documents["png"], 1)
    assert raised.value.fatal is True


@respx.mock
async def test_provider_error_inside_a_200(key, documents) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json={"error": {"code": 402, "message": "no credits"}})
    )

    with pytest.raises(PaymentRequired):
        await transcribe_page(key, "m", PROMPT, "yxyx_norm1000", documents["png"], 1)


def test_user_key_never_reveals_itself_in_a_repr(key) -> None:
    assert repr(key) == "UserKey(...)"
    assert "sk-or" not in repr(key)
