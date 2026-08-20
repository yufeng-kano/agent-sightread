"""The MCP endpoint (docs/mcp.md), driven by the official SDK client over ASGI.

Same rules as the REST tests: real Poppler, real queue, real claim cycle, zero upstream
traffic (docs/testing.md § Cost safety). `mcp_running` stands in for the app lifespan,
which `ASGITransport` never runs.
"""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import asynccontextmanager

import httpx2
import pytest
import respx
from httpx import AsyncClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from sightread.upstream.openrouter import CHAT_URL
from tests.conftest import mcp_running
from tests.test_parse_end_to_end import MODEL, _authorize, _drain_queue, _openrouter_stub

BASE_URL = "https://testserver"
CLAIM_POLL_SECONDS = 0.05
CLAIM_TIMEOUT_SECONDS = 20


@pytest.fixture
async def api_client(make_client, sessionmaker) -> AsyncClient:
    """A client holding an API key and a stored OpenRouter key, exactly like REST tests."""
    return await _authorize(make_client(), sessionmaker)


@asynccontextmanager
async def _mcp_session(client: AsyncClient, token: str | None = None):
    """An initialized MCP session against the app under test."""
    bearer = token if token is not None else _bearer(client)
    async with (
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=client.app),
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {bearer}"},
        ) as http,
        streamable_http_client(f"{BASE_URL}/mcp", http_client=http) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


def _bearer(client: AsyncClient) -> str:
    return client.headers["Authorization"].removeprefix("Bearer ")


def _payload(result) -> dict:
    """The tool's JSON payload, as a client would read it off the content block."""
    return json.loads(result.content[0].text)


async def _claim_when_queued(client: AsyncClient, sessionmaker):
    """Run worker claim cycles until one picks the tool's job up."""
    async with asyncio.timeout(CLAIM_TIMEOUT_SECONDS):
        while True:
            job_id = await _drain_queue(client, sessionmaker)
            if job_id is not None:
                return job_id
            await asyncio.sleep(CLAIM_POLL_SECONDS)


async def test_initialize_and_list_tools(api_client: AsyncClient) -> None:
    async with mcp_running(api_client), _mcp_session(api_client) as session:
        listing = await session.list_tools()

    tools = {tool.name: tool for tool in listing.tools}
    assert set(tools) == {"parse_document", "parse_image", "get_result"}
    assert "yxyx_norm1000" in tools["parse_document"].description
    assert "sightread://" in tools["parse_document"].description
    assert "no file paths" in tools["parse_document"].description
    assert "source" in tools["parse_document"].input_schema["required"]


async def test_an_unauthenticated_call_points_at_the_protected_resource_metadata(
    client: AsyncClient,
) -> None:
    async with mcp_running(client):
        response = await client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )

    assert response.status_code == 401
    challenge = response.headers["WWW-Authenticate"]
    assert challenge.startswith("Bearer ")
    # The pointer a Claude connector follows to find the authorization server (RFC 9728).
    assert (
        'resource_metadata="http://localhost:8000/.well-known/oauth-protected-resource"'
        in challenge
    )
    assert response.json()["error"]["type"] == "auth"


@respx.mock
async def test_parse_document_returns_the_finished_result(api_client, sessionmaker, documents):
    respx.post(CHAT_URL).mock(side_effect=_openrouter_stub)
    source = base64.b64encode(documents["mixed_pdf"].read_bytes()).decode()
    progress: list[tuple[float, float | None]] = []

    async def record(done: float, total: float | None, message: str | None) -> None:
        progress.append((done, total))

    async with mcp_running(api_client):
        async with _mcp_session(api_client) as session:
            call = asyncio.create_task(
                session.call_tool(
                    "parse_document",
                    {"source": source, "media_type": "application/pdf", "model": MODEL},
                    progress_callback=record,
                    read_timeout_seconds=CLAIM_TIMEOUT_SECONDS,
                )
            )
            job_id = await _claim_when_queued(api_client, sessionmaker)
            result = await call

        assert result.is_error is False, result.content
        payload = _payload(result)
        assert [page["method"] for page in payload["pages"]] == ["text_layer", "vision", "vision"]
        assert payload["meta"]["bbox_format"] == "yxyx_norm1000"
        assert payload["meta"]["cached"] is False
        assert "![fig2](sightread://p2/200,100,600,900)" in payload["markdown"]
        assert progress, "the tool reported no progress"

        # A fresh session still finds the job: that is how a disconnected client recovers.
        async with _mcp_session(api_client) as session:
            recovered = _payload(await session.call_tool("get_result", {"job_id": str(job_id)}))

    assert recovered["status"] == "succeeded"
    assert recovered["pages_done"] == 3
    assert recovered["result"]["markdown"] == payload["markdown"]


@respx.mock
async def test_a_second_identical_parse_is_served_from_the_cache(
    api_client, sessionmaker, documents
):
    respx.post(CHAT_URL).mock(side_effect=_openrouter_stub)
    source = base64.b64encode(documents["text_pdf"].read_bytes()).decode()

    async with mcp_running(api_client), _mcp_session(api_client) as session:
        call = asyncio.create_task(
            session.call_tool(
                "parse_document",
                {"source": source, "model": MODEL},
                read_timeout_seconds=CLAIM_TIMEOUT_SECONDS,
            )
        )
        await _claim_when_queued(api_client, sessionmaker)
        await call
        upstream_calls = respx.calls.call_count

        cached = _payload(
            await session.call_tool("parse_document", {"source": source, "model": MODEL})
        )

    assert cached["meta"]["cached"] is True
    assert respx.calls.call_count == upstream_calls


async def test_a_file_path_source_is_refused(api_client: AsyncClient) -> None:
    async with mcp_running(api_client), _mcp_session(api_client) as session:
        result = await session.call_tool(
            "parse_document", {"source": "/var/data/report.pdf", "model": MODEL}
        )

    assert result.is_error is True
    assert "file paths are not accepted" in result.content[0].text


async def test_get_result_refuses_a_job_this_user_does_not_own(api_client: AsyncClient) -> None:
    async with mcp_running(api_client), _mcp_session(api_client) as session:
        result = await session.call_tool(
            "get_result", {"job_id": "00000000-0000-4000-8000-000000000000"}
        )

    assert result.is_error is True
    assert "No such job" in result.content[0].text


async def test_an_invalid_token_never_reaches_a_tool(api_client: AsyncClient) -> None:
    async with mcp_running(api_client):
        response = await api_client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer sr_not-a-real-key",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["WWW-Authenticate"]
