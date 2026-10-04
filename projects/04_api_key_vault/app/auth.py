import os
import sqlite3
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request

from app.db import get_db

ALGORITHM = "HS256"
AUDIENCE = "api://keys"
ROLES = {"admin", "member"}
REQUIRED_CLAIMS = ["exp", "aud", "tid", "role", "uid"]


@dataclass
class Principal:
    uid: str
    tenant_id: str
    role: str
    scopes: set[str]


def jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not set")
    return secret


def _unauthorized() -> HTTPException:
    return HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


def authenticate(request: Request, db: sqlite3.Connection = Depends(get_db)) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    try:
        claims = jwt.decode(
            token,
            jwt_secret(),
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError:
        raise _unauthorized()
    if claims["role"] not in ROLES or not all(isinstance(claims[k], str) for k in ("tid", "uid")):
        raise _unauthorized()
    path_tenant = request.path_params.get("tenant_id")
    if path_tenant is not None and claims["tid"] != path_tenant:
        raise _unauthorized()
    user = db.execute(
        "SELECT tenant_id, role FROM users WHERE uid = ?", (claims["uid"],)
    ).fetchone()
    if user is None or user["role"] != claims["role"] or user["tenant_id"] != claims["tid"]:
        raise _unauthorized()
    scope = claims.get("scope", "")
    scopes = set(scope.split()) if isinstance(scope, str) else set()
    return Principal(uid=claims["uid"], tenant_id=claims["tid"], role=claims["role"], scopes=scopes)


def require(scope: str, *roles: str):
    """Dependency: authenticated, role in `roles`, and `scope` granted."""

    def dependency(principal: Principal = Depends(authenticate)) -> Principal:
        if principal.role not in roles or scope not in principal.scopes:
            raise HTTPException(403, "forbidden")
        return principal

    return dependency
