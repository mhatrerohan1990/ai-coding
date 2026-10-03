"""Mint a dev JWT for Quota Gate.

    python scripts/mint_token.py                      # org_1 admin
    python scripts/mint_token.py org_2 quota.check    # org_2 service token
"""
import os
import sys
import time

import jwt

tenant = sys.argv[1] if len(sys.argv) > 1 else "org_1"
scopes = sys.argv[2:] or ["quota.admin"]

claims = {
    "iss": os.environ.get("QUOTA_GATE_ISSUER", "https://idp.example.test"),
    "aud": "api://quota-gate",
    "exp": int(time.time()) + 3600,
    "sub": f"dev-{tenant}",
    "tid": tenant,
    "scp": scopes,
}
secret = os.environ.get("QUOTA_GATE_JWT_SECRET", "dev-secret-change-me")
print(jwt.encode(claims, secret, algorithm="HS256"))
