"""Shared test fixtures.

Database: set `TEST_DATABASE_URL` (or `DATABASE_URL`) to run the suite against a real
PostgreSQL — e.g. `docker compose up -d pg` then

    TEST_DATABASE_URL=postgresql+asyncpg://sightread:sightread@127.0.0.1:5432/sightread \
        uv run pytest

Without it the suite falls back to a throwaway SQLite file so `uv run pytest` works with
no services and no network. The models carry SQLite variants for the two PostgreSQL-only
types (JSONB and timestamptz) precisely so this fallback stays honest.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from sightread.config import Settings
from sightread.db.models import Base
from sightread.db.session import create_sessionmaker
from sightread.main import create_app

TEST_SECRET_KEY = "test-secret-key-not-a-real-one"
CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest_asyncio.fixture
async def sessionmaker(tmp_path):
    url = DATABASE_URL or f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield create_sessionmaker(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def make_client(sessionmaker) -> AsyncIterator[Callable[..., AsyncClient]]:
    """Build a client for an app with the given settings overrides.

    The app's sessionmaker is injected directly, so no lifespan and no live database are
    needed. `https://` base URL so the `Secure` session cookie is stored by httpx.
    """
    opened: list[AsyncClient] = []

    def _make(**overrides) -> AsyncClient:
        settings = Settings(
            **{
                "app_env": "local",
                "auth_dev_mode": True,
                "secret_key": TEST_SECRET_KEY,
                "database_url": "sqlite+aiosqlite://",
                **overrides,
            }
        )
        app = create_app(settings)
        app.state.sessionmaker = sessionmaker
        client = AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")
        opened.append(client)
        return client

    yield _make
    for client in opened:
        await client.aclose()


@pytest.fixture
def client(make_client) -> AsyncClient:
    return make_client()


@pytest_asyncio.fixture
async def signed_in(client: AsyncClient) -> AsyncClient:
    response = await client.post("/api/auth/dev-login", headers=CSRF_HEADERS)
    assert response.status_code == 200
    return client
