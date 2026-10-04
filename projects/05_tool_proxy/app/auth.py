import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole

AUDIENCE = "api://agent-proxy"
ALGORITHM = "HS256"

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def decode_user_token(token: str) -> dict:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not set")
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            options={"require": ["aud", "sub", "tid", "role"]},
        )
    except jwt.InvalidTokenError:
        raise _unauthorized("invalid token")


def require_admin(
    tenant_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Admin APIs: valid JWT, tid == path tenant, role claim admin, and sub is an
    enabled admin user of that tenant in the db."""
    if credentials is None:
        raise _unauthorized("missing token")
    claims = decode_user_token(credentials.credentials)

    if claims["tid"] != tenant_id:
        raise _forbidden("tenant mismatch")
    if claims["role"] != UserRole.ADMIN.value:
        raise _forbidden("admin role required")

    user = db.scalar(
        select(User).where(User.id == claims["sub"], User.tenant_id == tenant_id)
    )
    if user is None or not user.enabled or user.role != UserRole.ADMIN:
        raise _forbidden("admin role required")
    return user
