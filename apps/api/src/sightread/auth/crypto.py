"""Credential cryptography (docs/auth.md).

Two rules, strictly separated:

- Anything we only ever *verify* (session tokens, API keys) is stored as a SHA-256 hash.
- The one credential we must *replay* upstream (the user's OpenRouter key) is stored as
  AES-256-GCM ciphertext, keyed by HKDF-SHA256 over ``SECRET_KEY``.

Nothing here ever logs or returns plaintext.
"""

from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

OPENROUTER_KEY_CONTEXT = b"openrouter-key-v1"
NONCE_BYTES = 12


def hash_token(token: str) -> str:
    """SHA-256 hex digest used for session tokens, API keys and OAuth grant tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _openrouter_aead(secret_key: str) -> AESGCM:
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=OPENROUTER_KEY_CONTEXT,
    ).derive(secret_key.encode("utf-8"))
    return AESGCM(derived)


def encrypt_openrouter_key(secret_key: str, plaintext: str) -> bytes:
    """Return ``nonce || ciphertext``; a fresh random nonce is used for every encryption."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + _openrouter_aead(secret_key).encrypt(nonce, plaintext.encode("utf-8"), None)


def decrypt_openrouter_key(secret_key: str, blob: bytes) -> str:
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    return _openrouter_aead(secret_key).decrypt(nonce, ciphertext, None).decode("utf-8")


def mask_openrouter_key(plaintext: str) -> str:
    """Display form: leading provider prefix, elision, last four characters."""
    if len(plaintext) <= 12:
        return "..." + plaintext[-2:]
    return f"{plaintext[:8]}...{plaintext[-4:]}"
