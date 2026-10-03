"""Invite tokens have the form `<invite_id>.<secret>`.

The invite_id is a public, indexed lookup key. The secret carries the entropy and
is never stored; only its SHA-256 hash is. Neither part contains a '.'.
"""

import hashlib
import hmac
import secrets

SECRET_BYTES = 32  # 256 bits, above the 128-bit minimum
ID_BYTES = 16


def new_invite_id() -> str:
    return secrets.token_urlsafe(ID_BYTES)


def new_secret() -> str:
    return secrets.token_urlsafe(SECRET_BYTES)


def format_token(invite_id: str, secret: str) -> str:
    return f"{invite_id}.{secret}"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def parse(token: str) -> tuple[str, str] | None:
    """Split a token into (invite_id, secret), or None if malformed."""
    invite_id, sep, secret = token.partition(".")
    if not sep or not invite_id or not secret or "." in secret:
        return None
    return invite_id, secret


def verify(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(secret), stored_hash)
