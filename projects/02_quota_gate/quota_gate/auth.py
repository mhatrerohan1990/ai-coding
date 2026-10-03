from dataclasses import dataclass
from functools import wraps

import jwt
from flask import g, request

from quota_gate.errors import Forbidden, InvalidRequest, InvalidToken

AUDIENCE = "api://quota-gate"
ADMIN_SCOPE = "quota.admin"
CHECK_SCOPE = "quota.check"


@dataclass(frozen=True)
class Principal:
    """Who is calling, taken only from a verified JWT."""

    issuer: str
    tenant_id: str
    subject: str
    scopes: frozenset

    def require_scope(self, scope):
        if scope not in self.scopes:
            raise Forbidden(f"missing required scope '{scope}'")

    def require_tenant(self, tenant_id):
        if tenant_id != self.tenant_id:
            raise Forbidden("token is not authorized for this tenant")


class TokenVerifier:
    def __init__(self, secret, issuer):
        self._secret = secret
        self._issuer = issuer

    def authenticate(self, authorization_header):
        token = self._bearer_token(authorization_header)
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as err:
            raise InvalidToken(f"invalid token: {err}") from None

        tenant_id, subject, scopes = claims.get("tid"), claims["sub"], claims.get("scp")
        if not _non_empty_str(tenant_id):
            raise InvalidToken("invalid token: 'tid' must be a non-empty string")
        if not _non_empty_str(subject):
            raise InvalidToken("invalid token: 'sub' must be a non-empty string")
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise InvalidToken("invalid token: 'scp' must be a list of strings")
        return Principal(claims["iss"], tenant_id, subject, frozenset(scopes))

    @staticmethod
    def _bearer_token(header):
        parts = (header or "").split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise InvalidToken("expected 'Authorization: Bearer <token>'")
        return parts[1]


def _non_empty_str(value):
    return isinstance(value, str) and value != ""


def tenant_from_path(**view_args):
    return view_args.get("tenant_id")


def tenant_from_body(**_view_args):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise InvalidRequest("request body must be a JSON object")
    return body.get("tenant_id")


def requires_scope(verifier, scope, tenant_from=tenant_from_path):
    """Guard a route that acts on one tenant.

    401 if the token is bad, 403 if it lacks `scope` or belongs to another tenant.
    `tenant_from(**view_args)` says which tenant the request targets (URL path by
    default). The verified Principal is left on flask.g.principal.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            principal = verifier.authenticate(request.headers.get("Authorization"))
            principal.require_scope(scope)
            tenant_id = tenant_from(**kwargs)
            if not _non_empty_str(tenant_id):  # checked after authn/authz, so 401/403 win
                raise InvalidRequest("tenant_id must be a non-empty string")
            principal.require_tenant(tenant_id)
            g.principal = principal
            return view(*args, **kwargs)

        return wrapper

    return decorator
