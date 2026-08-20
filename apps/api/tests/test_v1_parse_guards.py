"""Request-level guards on `POST /v1/parse`: limits, caps, bad input and model choice."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

import httpx
import respx
from httpx import AsyncClient

from sightread.db.models import Job, utcnow
from sightread.upstream.openrouter import MODELS_URL, reset_models_cache
from tests.conftest import CSRF_HEADERS

MODEL = "vendor/vision-model"


async def _keyed_client(client: AsyncClient) -> AsyncClient:
    await client.post("/api/auth/dev-login", headers=CSRF_HEADERS)
    created = await client.post("/api/keys", json={"name": "test"}, headers=CSRF_HEADERS)
    client.headers["Authorization"] = f"Bearer {created.json()['key']}"
    return client


async def _upload(client: AsyncClient, path: Path, **fields) -> httpx.Response:
    return await client.post(
        "/v1/parse",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"model": MODEL, **fields},
    )


async def test_parse_requires_an_api_key(client: AsyncClient, documents) -> None:
    response = await _upload(client, documents["text_pdf"])
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "auth"


async def test_a_corrupt_pdf_is_rejected_before_a_job_exists(
    client: AsyncClient, sessionmaker, documents
) -> None:
    await _keyed_client(client)
    response = await _upload(client, documents["corrupt_pdf"])

    assert response.status_code == 400
    assert "PDF" in response.json()["error"]["message"]
    upload_dir = Path(client.app.state.settings.upload_dir)
    assert list(upload_dir.iterdir()) == []


async def test_the_page_cap_is_enforced(make_client, documents) -> None:
    client = await _keyed_client(make_client(page_cap=2))
    response = await _upload(client, documents["mixed_pdf"])

    assert response.status_code == 400
    assert "page cap" in response.json()["error"]["message"]


async def test_the_size_cap_is_enforced_while_streaming(make_client, documents) -> None:
    # A cap just under the file size: the cheap content-length check lets this through, so
    # the streaming copy is what has to stop it.
    size = documents["mixed_pdf"].stat().st_size
    client = await _keyed_client(make_client(upload_max_bytes=size - 1))
    response = await _upload(client, documents["mixed_pdf"])

    assert response.status_code == 413
    upload_dir = Path(client.app.state.settings.upload_dir)
    assert list(upload_dir.iterdir()) == []


async def test_an_oversized_body_is_refused_before_it_is_read(make_client, documents) -> None:
    client = await _keyed_client(make_client(upload_max_bytes=64))
    response = await _upload(client, documents["mixed_pdf"])

    assert response.status_code == 413
    upload_dir = Path(client.app.state.settings.upload_dir)
    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


async def test_an_unsupported_media_type_is_rejected(client: AsyncClient, tmp_path) -> None:
    await _keyed_client(client)
    document = tmp_path / "notes.txt"
    document.write_text("plain text")

    response = await client.post(
        "/v1/parse",
        files={"file": (document.name, document.read_bytes(), "text/plain")},
        data={"model": MODEL},
    )
    assert response.status_code == 400


async def test_an_invalid_page_selection_is_rejected(client: AsyncClient, documents) -> None:
    await _keyed_client(client)
    response = await _upload(client, documents["mixed_pdf"], pages="4-9")

    assert response.status_code == 400
    assert "outside" in response.json()["error"]["message"]


async def test_the_per_user_running_cap_returns_429(
    client: AsyncClient, sessionmaker, documents
) -> None:
    await _keyed_client(client)
    user_id = (await client.get("/api/me")).json()["user"]["id"]

    async with sessionmaker() as db:
        for index in range(2):
            db.add(
                Job(
                    user_id=user_id,
                    kind="pdf",
                    filename="busy.pdf",
                    media_type="application/pdf",
                    size_bytes=10,
                    sha256=str(index) * 64,
                    pages_spec="",
                    model=MODEL,
                    profile=None,
                    profile_version=0,
                    pipeline_version=1,
                    bbox_format="yxyx_norm1000",
                    status="running",
                    page_count=1,
                    started_at=utcnow(),
                )
            )
        await db.commit()

    response = await _upload(client, documents["text_pdf"])

    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit"
    assert response.headers["Retry-After"] == "30"


async def test_the_json_base64_fallback_creates_the_same_job(
    client: AsyncClient, sessionmaker, documents
) -> None:
    await _keyed_client(client)
    encoded = base64.b64encode(documents["text_pdf"].read_bytes()).decode("ascii")

    response = await client.post(
        "/v1/parse",
        json={
            "source": encoded,
            "filename": "text.pdf",
            "media_type": "application/pdf",
            "model": MODEL,
        },
    )

    assert response.status_code == 202
    async with sessionmaker() as db:
        job = await db.get(Job, uuid.UUID(response.json()["job_id"]))
    assert job.kind == "pdf"
    assert job.size_bytes == documents["text_pdf"].stat().st_size
    assert Path(job.source_path).exists()


async def test_broken_base64_is_rejected(client: AsyncClient, documents) -> None:
    await _keyed_client(client)
    response = await client.post(
        "/v1/parse", json={"source": "not base64 at all!!", "model": MODEL}
    )
    assert response.status_code == 400


async def test_a_job_needs_a_model_or_a_profile(client: AsyncClient, documents) -> None:
    await _keyed_client(client)
    response = await client.post(
        "/v1/parse",
        files={"file": ("text.pdf", documents["text_pdf"].read_bytes(), "application/pdf")},
    )

    assert response.status_code == 400
    assert "No model configured" in response.json()["error"]["message"]


@respx.mock
async def test_a_preset_profile_resolves_its_model_from_the_catalog(
    client: AsyncClient, sessionmaker, documents
) -> None:
    reset_models_cache()
    respx.get(MODELS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "google/gemini-3.5-flash",
                        "created": 200,
                        "architecture": {"input_modalities": ["text", "image"]},
                    }
                ]
            },
        )
    )
    await _keyed_client(client)

    response = await client.post(
        "/v1/parse",
        files={"file": ("text.pdf", documents["text_pdf"].read_bytes(), "application/pdf")},
        data={"profile": "gemini-yxyx"},
    )

    assert response.status_code == 202
    async with sessionmaker() as db:
        job = await db.get(Job, uuid.UUID(response.json()["job_id"]))
    assert job.model == "google/gemini-3.5-flash"
    assert job.profile == "gemini-yxyx"
    assert job.bbox_format == "yxyx_norm1000"
    reset_models_cache()


async def test_an_unknown_profile_is_rejected(client: AsyncClient, documents) -> None:
    await _keyed_client(client)
    response = await client.post(
        "/v1/parse",
        files={"file": ("text.pdf", documents["text_pdf"].read_bytes(), "application/pdf")},
        data={"profile": "not-a-profile"},
    )
    assert response.status_code == 400


async def test_jobs_of_other_users_are_invisible(make_client, sessionmaker, documents) -> None:
    owner = await _keyed_client(make_client())
    accepted = await _upload(owner, documents["text_pdf"])
    job_id = accepted.json()["job_id"]

    stranger = make_client()
    await stranger.post("/api/auth/dev-login", headers=CSRF_HEADERS)
    # A second identity: the dev login always returns the same user, so use a raw key row.
    async with sessionmaker() as db:
        from sightread.auth.api_keys import create_api_key
        from sightread.db.models import User

        other = User(google_sub="stranger", email="stranger@example.com")
        db.add(other)
        await db.flush()
        _, plaintext = await create_api_key(db, other, "stranger")
        await db.commit()

    stranger.headers["Authorization"] = f"Bearer {plaintext}"
    assert (await stranger.get(f"/v1/jobs/{job_id}")).status_code == 404
    assert (await stranger.get(f"/v1/jobs/{job_id}/result")).status_code == 404
