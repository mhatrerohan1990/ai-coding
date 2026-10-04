"""Print a signed JWT for manual testing.

    JWT_SECRET=... python scripts/make_token.py --tid t1 --role admin
"""
import argparse
import os
import time

import jwt

p = argparse.ArgumentParser()
p.add_argument("--tid", default="t1")
p.add_argument("--uid", help="default: u-<role>-<tid>")
p.add_argument("--role", default="admin", choices=["admin", "member"])
p.add_argument("--scope", default="create revoke rotate introspect list")
p.add_argument("--ttl", type=int, default=3600)
a = p.parse_args()
uid = a.uid or f"u-{a.role}-{a.tid}"

print(jwt.encode(
    {"sub": "dev", "tid": a.tid, "uid": uid, "role": a.role, "scope": a.scope,
     "aud": "api://keys", "exp": int(time.time()) + a.ttl},
    os.environ["JWT_SECRET"], algorithm="HS256"))
