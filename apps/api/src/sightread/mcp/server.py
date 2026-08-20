"""The MCP endpoint: streamable HTTP at `POST /mcp`, mounted in the same app (docs/mcp.md).

A shell and nothing more. Every tool is: authenticate (the same bearer as `/v1`), call
`jobs.intake`, follow `jobs.events`, hand back the same payload REST returns. No parsing
decision, no model choice and no queue knowledge lives here, so an MCP spec change touches
this file alone (docs/project-structure.md § Boundaries).
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from ..auth.deps import bearer_credential, resolve_bearer
from ..db.models import Job, Result, User
from ..errors import error_response
from ..jobs import events
from ..jobs.intake import PDF_MEDIA_TYPE, base64_chunks, cached_payload, submit_parse
from ..jobs.runner import result_payload

MCP_PATH = "/mcp"
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"

# A source that looks like a filesystem path is refused outright: this is a hosted service
# and a server-side path would be a local file read, not an upload (docs/product.md § 3).
PATH_LIKE = re.compile(r"^(/|\./|\.\./|~|file://|[A-Za-z]:[\\/])")

COORDINATE_CONTRACT = (
    "Figures come back as `![figN](sightread://pPAGE/x1,y1,x2,y2)` placeholders with the "
    "caption on the next line, plus a `figures` array. Coordinates use meta.bbox_format "
    "(yxyx_norm1000: 0-1000 of page height/width). You crop, we don't — page dimensions "
    "are in `pages`."
)

# The authenticated user for the request being served. Set by the ASGI guard below and read
# by the tools; the streamable-HTTP transport runs each request's handler in a task spawned
# from that request, so the value a tool sees is the one its own caller presented.
_current_user_id: ContextVar[int | None] = ContextVar("sightread_mcp_user_id", default=None)


async def _current_user(db: AsyncSession) -> User:
    user_id = _current_user_id.get()
    user = (
        None
        if user_id is None
        else (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    )
    if user is None:
        raise PermissionError("This MCP session is not authenticated")
    return user


def _check_source(source: str) -> None:
    if not source.strip():
        raise ValueError("source is required: base64-encoded document bytes")
    if PATH_LIKE.match(source.strip()):
        raise ValueError("source must be base64 document bytes; file paths are not accepted")


async def _run_parse(
    app: FastAPI,
    ctx: Context,
    *,
    source: str,
    media_type: str,
    pages: str | None,
    model: str | None,
    profile: str | None,
    force: bool,
) -> dict[str, Any]:
    """Queue the parse, report progress as pages land, return the finished result."""
    _check_source(source)
    settings = app.state.settings
    sessionmaker = app.state.sessionmaker

    async with sessionmaker() as db:
        user = await _current_user(db)
        submission = await submit_parse(
            db,
            settings,
            user=user,
            chunks=base64_chunks(source),
            media_type=media_type,
            model=model,
            profile_id=profile,
            pages=pages,
            force=force,
        )
    if submission.cached is not None:
        return cached_payload(submission.cached)

    job_id = submission.job.id
    # The worker owns the job from here: a client that disconnects only stops watching, and
    # `get_result` picks the same job up later (docs/mcp.md).
    async for event, data in events.iter_job_events(sessionmaker, settings.database_url, job_id):
        if event == events.PROGRESS:
            await ctx.report_progress(
                progress=data["pages_done"],
                total=data["page_count"],
                message=f"page {data['page']} ({data['method']})",
            )
        elif event == events.DONE:
            return data
        elif event == events.ERROR:
            raise RuntimeError(f"{data['error']['message']} (job_id {job_id})")
    raise RuntimeError(f"The job stream ended without a result (job_id {job_id})")


def build_server(app: FastAPI) -> MCPServer:
    """The MCP server and its three tools (docs/mcp.md § Tools)."""
    server = MCPServer(
        "agent-sightread",
        instructions=(
            "Parse PDFs and images into markdown with figure bounding boxes. Upload bytes "
            "as base64; the service never reads files from a path. " + COORDINATE_CONTRACT
        ),
    )

    @server.tool(
        description=(
            "Parse a PDF into markdown. `source` is the base64-encoded PDF itself — no file "
            "paths, this is a hosted service. Optional `pages` ('1-5,8'), `model`, `profile`, "
            "and `force` (bypass the per-user dedup cache). Returns markdown, per-page method "
            "and dimensions, and figures. " + COORDINATE_CONTRACT
        )
    )
    async def parse_document(
        ctx: Context,
        source: str,
        media_type: str = PDF_MEDIA_TYPE,
        pages: str | None = None,
        model: str | None = None,
        profile: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        return await _run_parse(
            app,
            ctx,
            source=source,
            media_type=media_type,
            pages=pages,
            model=model,
            profile=profile,
            force=force,
        )

    @server.tool(
        description=(
            "Parse one image (jpg/png/webp/heic) into markdown. `source` is the base64-encoded "
            "image itself — no file paths. Optional `model`, `profile`, `force`. "
            + COORDINATE_CONTRACT
        )
    )
    async def parse_image(
        ctx: Context,
        source: str,
        media_type: str = "image/png",
        model: str | None = None,
        profile: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        return await _run_parse(
            app,
            ctx,
            source=source,
            media_type=media_type,
            pages=None,
            model=model,
            profile=profile,
            force=force,
        )

    @server.tool(
        description=(
            "Fetch a parse job by id: its status, and `result` (the same payload parse_document "
            "returns) once it finished. Use it after a disconnect — the job keeps running."
        )
    )
    async def get_result(job_id: str) -> dict[str, Any]:
        try:
            wanted = uuid.UUID(job_id)
        except ValueError as exc:
            raise ValueError("job_id must be a UUID") from exc

        async with app.state.sessionmaker() as db:
            user = await _current_user(db)
            job = (
                await db.execute(select(Job).where(Job.id == wanted, Job.user_id == user.id))
            ).scalar_one_or_none()
            if job is None:
                raise ValueError("No such job")
            result = (
                await db.execute(select(Result).where(Result.job_id == wanted))
            ).scalar_one_or_none()

        return {
            "job_id": str(job.id),
            "status": job.status,
            "page_count": job.page_count,
            "pages_done": job.pages_done,
            "error": job.error,
            "result": result_payload(result) if result is not None else None,
        }

    return server


class BearerGuard:
    """Bearer auth in front of the MCP transport.

    A 401 from here carries `WWW-Authenticate` with the protected-resource metadata URL —
    that pointer is what makes a Claude connector discover the authorization server and
    start the OAuth flow (docs/auth.md § 4, RFC 9728).
    """

    def __init__(self, app: FastAPI, transport) -> None:
        self._app = app
        self._transport = transport

    def _challenge(self, invalid: bool) -> dict[str, str]:
        issuer = self._app.state.settings.app_url.rstrip("/")
        parts = [f'resource_metadata="{issuer}{PROTECTED_RESOURCE_PATH}"']
        if invalid:
            parts.insert(0, 'error="invalid_token"')
        return {"WWW-Authenticate": "Bearer " + ", ".join(parts)}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        credential = bearer_credential(Request(scope))
        user = None
        if credential is not None:
            async with self._app.state.sessionmaker() as db:
                user = await resolve_bearer(db, credential)
        if user is None:
            response = error_response(
                401,
                "auth",
                "Invalid or missing bearer token",
                self._challenge(invalid=credential is not None),
            )
            await response(scope, receive, send)
            return

        token = _current_user_id.set(user.id)
        try:
            await self._transport(scope, receive, send)
        finally:
            _current_user_id.reset(token)


def mount_mcp(app: FastAPI) -> None:
    """Register `POST /mcp` on the FastAPI app and remember how to run its session manager."""
    server = build_server(app)
    transport = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        # Stateless: every request carries its own bearer and is served on its own
        # transport, so a connector never depends on server-side session affinity.
        stateless_http=True,
        # Host/Origin filtering belongs to Caddy in front of us; this endpoint is
        # authenticated with a bearer a browser cannot mint (docs/deployment.md).
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    # A Route (not a Mount) so the path stays exactly `/mcp` for every method.
    app.router.routes.append(Route(MCP_PATH, endpoint=BearerGuard(app, transport)))
    app.state.mcp = server


@asynccontextmanager
async def mcp_session_manager(app: FastAPI):
    """Run the MCP session manager for the lifetime of the app (required by the SDK)."""
    async with app.state.mcp.session_manager.run():
        yield
