"""OAuth 2.1 authorization server endpoints (docs/auth.md § 4).

Two audiences, two error shapes: `/.well-known/*`, `/oauth/register` and `/oauth/token` are
read by OAuth clients and answer in RFC form (`{"error": "...", "error_description": "..."}`),
while `/oauth/authorize` is read by a human in a browser and answers in HTML. The app's own
error envelope stays on `/v1` and `/api`, where its clients live.

The consent page is served from here on purpose: the browser lands on the API origin
holding the session cookie, and a redirect through the Nuxt app would only add a hop that
can lose the request (docs/auth.md).
"""

from __future__ import annotations

import html
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..auth.deps import AppSettings, DbSession
from ..auth.oauth_as import (
    CODE_CHALLENGE_METHOD,
    SCOPE,
    RegistrationError,
    exchange_code,
    get_client,
    issue_code,
    refresh_tokens,
    register_client,
)
from ..auth.oidc import POST_LOGIN_KEY
from ..auth.sessions import SESSION_COOKIE, resolve_session
from ..config import Settings
from ..db.models import OAuthClient, User

router = APIRouter(tags=["oauth"])

# The Starlette session cookie also carries the consent CSRF token and, while a sign-in is
# in flight, the authorize request to come back to.
CONSENT_STATE_KEY = "oauth_consent"

MCP_PATH = "/mcp"
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _oauth_error(status_code: int, error: str, description: str) -> JSONResponse:
    """RFC 6749 § 5.2 / RFC 7591 § 3.2.2 error body — what an OAuth client knows how to read."""
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "error_description": description},
        headers=NO_STORE,
    )


BODY_STYLE = "font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem"


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    """The whole server-rendered surface: one unstyled, self-contained page."""
    return HTMLResponse(
        status_code=status_code,
        content=(
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title></head>"
            f"<body style='{BODY_STYLE}'>"
            f"<h1 style='font-size:1.25rem'>{html.escape(title)}</h1>{body}</body></html>"
        ),
    )


# --- discovery ------------------------------------------------------------------------


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata(settings: AppSettings) -> JSONResponse:
    """RFC 8414 metadata; the issuer is this API's public origin."""
    issuer = settings.app_url.rstrip("/")
    return JSONResponse(
        {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize",
            "token_endpoint": f"{issuer}/oauth/token",
            "registration_endpoint": f"{issuer}/oauth/register",
            "scopes_supported": [SCOPE],
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": [CODE_CHALLENGE_METHOD],
        }
    )


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata(settings: AppSettings) -> JSONResponse:
    """RFC 9728 metadata for the one protected resource: the MCP endpoint (docs/mcp.md).

    Also served under the path-suffixed form, which is where a client that starts from
    `<origin>/mcp` looks first.
    """
    issuer = settings.app_url.rstrip("/")
    return JSONResponse(
        {
            "resource": f"{issuer}{MCP_PATH}",
            "authorization_servers": [issuer],
            "scopes_supported": [SCOPE],
            "bearer_methods_supported": ["header"],
        }
    )


# --- dynamic client registration ------------------------------------------------------


@router.post("/oauth/register", status_code=201)
async def register(request: Request, db: DbSession, settings: AppSettings):
    """Open DCR (RFC 7591). Public clients only: no secret is issued, PKCE is mandatory."""
    try:
        body = await request.json()
    except ValueError:
        return _oauth_error(400, "invalid_client_metadata", "Body must be JSON")
    if not isinstance(body, dict):
        return _oauth_error(400, "invalid_client_metadata", "Body must be a JSON object")

    redirect_uris = body.get("redirect_uris")
    if not isinstance(redirect_uris, list) or not all(isinstance(u, str) for u in redirect_uris):
        return _oauth_error(400, "invalid_redirect_uri", "redirect_uris must be a list of strings")

    name = body.get("client_name")
    try:
        client = await register_client(
            db,
            client_name=name if isinstance(name, str) else "",
            redirect_uris=redirect_uris,
            allow_localhost=settings.app_env == "local",
        )
    except RegistrationError as exc:
        return _oauth_error(400, exc.error, exc.description)
    await db.commit()

    return JSONResponse(
        status_code=201,
        headers=NO_STORE,
        content={
            "client_id": client.client_id,
            "client_id_issued_at": int(client.created_at.timestamp()),
            "client_name": client.client_name,
            "redirect_uris": client.redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
    )


# --- authorization ---------------------------------------------------------------------


async def _validated_request(
    db: DbSession, client_id: str, redirect_uri: str
) -> OAuthClient | HTMLResponse:
    """Client and redirect URI checks whose failure must *not* redirect (RFC 6749 § 4.1.2.1)."""
    client = await get_client(db, client_id) if client_id else None
    if client is None:
        return _page("Unknown client", "<p>This connector is not registered here.</p>", 400)
    if redirect_uri not in (client.redirect_uris or []):
        return _page(
            "Invalid redirect URI",
            "<p>The redirect URI does not match the one this connector registered.</p>",
            400,
        )
    return client


def _redirect_with_error(redirect_uri: str, state: str, error: str) -> RedirectResponse:
    query = {"error": error, **({"state": state} if state else {})}
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{urlencode(query)}", status_code=302)


async def _session_user(request: Request, db: DbSession) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    return await resolve_session(db, token) if token else None


def _sign_in_page(request: Request, settings: Settings) -> RedirectResponse | HTMLResponse:
    """Send the browser to Google, remembering the authorize request to come back to."""
    if settings.google_oidc_configured:
        request.session[POST_LOGIN_KEY] = request.url.path + (
            f"?{request.url.query}" if request.url.query else ""
        )
        return RedirectResponse("/api/auth/login", status_code=302)
    hint = (
        "<p>This deployment has no Google sign-in configured. Sign in through the web app "
        f"at <code>{html.escape(settings.web_url)}</code> (dev login), then reload this page.</p>"
        if settings.dev_login_enabled
        else "<p>Sign-in is unavailable on this deployment.</p>"
    )
    return _page("Sign in required", hint, 401)


@router.get("/oauth/authorize")
async def authorize(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    client_id: str = "",
    redirect_uri: str = "",
    response_type: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
    state: str = "",
    scope: str = "",
):
    """Consent screen for a signed-in user; anything else is a redirect or an error page.

    `resource` (RFC 8707) is accepted and ignored: this AS protects exactly one resource.
    """
    client = await _validated_request(db, client_id, redirect_uri)
    if isinstance(client, HTMLResponse):
        return client
    if response_type != "code":
        return _redirect_with_error(redirect_uri, state, "unsupported_response_type")
    if not code_challenge or code_challenge_method != CODE_CHALLENGE_METHOD:
        return _redirect_with_error(redirect_uri, state, "invalid_request")

    user = await _session_user(request, db)
    if user is None:
        return _sign_in_page(request, settings)

    consent_token = secrets.token_urlsafe(16)
    request.session[CONSENT_STATE_KEY] = consent_token
    fields = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "scope": scope or SCOPE,
        "consent_token": consent_token,
    }
    hidden = "".join(
        f"<input type='hidden' name='{name}' value='{html.escape(value)}'>"
        for name, value in fields.items()
    )
    body = (
        f"<p><strong>{html.escape(client.client_name)}</strong> wants to parse documents as "
        f"<strong>{html.escape(user.email)}</strong>. Parsing bills your own OpenRouter key.</p>"
        f"<form method='post' action='/oauth/authorize'>{hidden}"
        "<button name='decision' value='approve' type='submit'>Approve</button> "
        "<button name='decision' value='deny' type='submit'>Deny</button></form>"
    )
    return _page("Authorize connector", body)


@router.post("/oauth/authorize")
async def authorize_decision(
    request: Request,
    db: DbSession,
    consent_token: Annotated[str, Form()] = "",
    decision: Annotated[str, Form()] = "",
    client_id: Annotated[str, Form()] = "",
    redirect_uri: Annotated[str, Form()] = "",
    state: Annotated[str, Form()] = "",
    code_challenge: Annotated[str, Form()] = "",
):
    """Approve or deny. The consent token pairs with the session cookie against CSRF."""
    expected = request.session.pop(CONSENT_STATE_KEY, None)
    if not expected or not secrets.compare_digest(expected, consent_token):
        return _page("Expired form", "<p>Start the connector flow again.</p>", 400)

    client = await _validated_request(db, client_id, redirect_uri)
    if isinstance(client, HTMLResponse):
        return client
    user = await _session_user(request, db)
    if user is None:
        return _page("Sign in required", "<p>Your session expired. Sign in and retry.</p>", 401)
    if decision != "approve":
        return _redirect_with_error(redirect_uri, state, "access_denied")

    code = await issue_code(
        db, client=client, user=user, redirect_uri=redirect_uri, code_challenge=code_challenge
    )
    await db.commit()
    query = {"code": code, **({"state": state} if state else {})}
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{urlencode(query)}", status_code=302)


# --- token -----------------------------------------------------------------------------


@router.post("/oauth/token")
async def token(
    db: DbSession,
    grant_type: Annotated[str, Form()] = "",
    code: Annotated[str, Form()] = "",
    code_verifier: Annotated[str, Form()] = "",
    redirect_uri: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str, Form()] = "",
    client_id: Annotated[str, Form()] = "",
):
    """Code + PKCE or a refresh token in, an access/refresh pair out (docs/auth.md § 4)."""
    if not client_id or await get_client(db, client_id) is None:
        return _oauth_error(401, "invalid_client", "Unknown client_id")

    if grant_type == "authorization_code":
        if not code or not code_verifier:
            return _oauth_error(400, "invalid_request", "code and code_verifier are required")
        issued = await exchange_code(
            db,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )
    elif grant_type == "refresh_token":
        if not refresh_token:
            return _oauth_error(400, "invalid_request", "refresh_token is required")
        issued = await refresh_tokens(db, refresh_token=refresh_token, client_id=client_id)
    else:
        return _oauth_error(
            400, "unsupported_grant_type", "Use authorization_code or refresh_token"
        )

    if issued is None:
        await db.rollback()
        return _oauth_error(400, "invalid_grant", "The grant is invalid, expired or already used")
    await db.commit()

    return JSONResponse(
        headers=NO_STORE,
        content={
            "access_token": issued.access_token,
            "token_type": "Bearer",
            "expires_in": issued.expires_in,
            "refresh_token": issued.refresh_token,
            "scope": SCOPE,
        },
    )
