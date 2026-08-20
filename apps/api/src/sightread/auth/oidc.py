"""Google OIDC client (docs/auth.md § 1).

Authorization Code + PKCE via Authlib. The transient `state`/`code_verifier`/`nonce` live
in a short-lived signed Starlette session cookie; the durable credential is the
server-side session row created after the callback.
"""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import User, UserSettings

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
DEV_USER_EMAIL = "dev@localhost"
DEV_USER_SUB = "dev-local"


def build_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()
    oauth.register(
        name="google",
        server_metadata_url=GOOGLE_METADATA_URL,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )
    return oauth


async def upsert_user(db: AsyncSession, google_sub: str, email: str, name: str | None) -> User:
    """Users are keyed by the Google `sub`; email and name are refreshed on each sign-in."""
    user = (
        await db.execute(select(User).where(User.google_sub == google_sub))
    ).scalar_one_or_none()
    if user is None:
        user = User(google_sub=google_sub, email=email, name=name)
        db.add(user)
        await db.flush()
        db.add(UserSettings(user_id=user.id))
        await db.flush()
        return user
    user.email = email
    user.name = name
    await db.flush()
    return user
