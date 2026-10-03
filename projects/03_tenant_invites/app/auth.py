"""Authn (is this a valid token for this API?) and authz (may it act on this tenant?).

Tokens are `Authorization: Bearer <JWT>`, HS256, aud=api://invites, with required claims
exp, sub, tid (tenant id) and role. Authn failures are 401; authz failures are 403.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALGORITHMS = ["HS256"]  # pinned: never trust the token's own `alg` header
AUDIENCE = "api://invites"
REQUIRED_CLAIMS = ["exp", "aud", "sub", "tid", "role"]

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Claims:
    sub: str
    tid: str
    role: str


def get_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return secret


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or missing token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden.")


def decode_token(token: str) -> Claims:
    try:
        payload = jwt.decode(
            token,
            get_secret(),
            algorithms=ALGORITHMS,
            audience=AUDIENCE,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError:
        raise _unauthorized() from None
    values = [payload.get(k) for k in ("sub", "tid", "role")]
    if not all(isinstance(v, str) and v for v in values):
        raise _unauthorized()
    return Claims(*values)


def authenticate(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Claims:
    if creds is None:
        raise _unauthorized()
    return decode_token(creds.credentials)


def require_roles(*roles: str) -> Callable[..., Claims]:
    """Dependency: authenticated, token's tid == path tenant_id, and role in `roles`."""

    def dependency(tenant_id: str, claims: Claims = Depends(authenticate)) -> Claims:
        if claims.tid != tenant_id or claims.role not in roles:
            raise _forbidden()
        return claims

    return dependency


require_admin = require_roles(ROLE_ADMIN)
require_member_or_admin = require_roles(ROLE_ADMIN, ROLE_MEMBER)
