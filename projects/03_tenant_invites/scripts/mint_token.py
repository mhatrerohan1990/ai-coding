"""Mint a JWT for local testing (nothing in this app issues tokens).

    JWT_SECRET=... uv run python scripts/mint_token.py --tid t1 --role admin
"""

import argparse
import os
import time

import jwt

parser = argparse.ArgumentParser()
parser.add_argument("--tid", required=True, help="tenant id")
parser.add_argument("--role", default="admin", choices=["admin", "member"])
parser.add_argument("--sub", default="local-user")
parser.add_argument("--ttl", type=int, default=3600, help="seconds until expiry")
args = parser.parse_args()

print(
    jwt.encode(
        {
            "sub": args.sub,
            "tid": args.tid,
            "role": args.role,
            "aud": "api://invites",
            "exp": int(time.time()) + args.ttl,
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
)
