"""Project API keys for the data plane (docs/auth.md § 2).

Format ``sr_<32 url-safe chars>``. Shown exactly once at creation; stored as a SHA-256
hash plus a display string. Revocation is a soft delete.
"""

from __future__ import annotations

import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ApiKey, User, utcnow
from .crypto import hash_token

KEY_PREFIX = "sr_"
KEY_RANDOM_CHARS = 32


def generate_api_key() -> str:
    # token_urlsafe(24) is exactly 32 url-safe characters.
    return KEY_PREFIX + secrets.token_urlsafe(24)[:KEY_RANDOM_CHARS]


def display_prefix(key: str) -> str:
    """The `sr_...abc4` form stored alongside the hash and shown in listings."""
    return f"{KEY_PREFIX}...{key[-4:]}"


async def create_api_key(db: AsyncSession, user: User, name: str) -> tuple[ApiKey, str]:
    key = generate_api_key()
    row = ApiKey(user_id=user.id, name=name, key_hash=hash_token(key), prefix=display_prefix(key))
    db.add(row)
    await db.flush()
    return row, key


async def resolve_api_key(db: AsyncSession, presented: str) -> User | None:
    """Look the key up by hash and compare in constant time; touch `last_used_at`."""
    if not presented.startswith(KEY_PREFIX):
        return None
    key_hash = hash_token(presented)
    row = (await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))).scalar_one_or_none()
    if row is None or not hmac.compare_digest(row.key_hash, key_hash):
        return None
    if row.revoked_at is not None:
        return None
    row.last_used_at = utcnow()
    await db.commit()
    return (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
