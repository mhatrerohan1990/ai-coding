import time

import jwt

SECRET = "test-secret-test-secret-test-secret-0123456789"
UNSET = object()


def mint(
    tid="t1",
    role="admin",
    *,
    sub="u1",
    aud="api://invites",
    exp=UNSET,
    secret=SECRET,
    alg="HS256",
    omit=(),
) -> str:
    claims = {
        "sub": sub,
        "tid": tid,
        "role": role,
        "aud": aud,
        "exp": int(time.time()) + 3600 if exp is UNSET else exp,
    }
    for k in omit:
        claims.pop(k, None)
    return jwt.encode(claims, secret, algorithm=alg)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def as_(tid="t1", role="admin") -> dict[str, str]:
    return bearer(mint(tid, role))
