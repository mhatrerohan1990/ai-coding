"""Mint a dev JWT for Quota Gate.

    python scripts/mint_token.py                      # org_1 admin, our issuer
    python scripts/mint_token.py org_2 quota.check    # org_2 service token, our issuer
    python scripts/mint_token.py --partner            # org_3 admin, partner issuer
    python scripts/mint_token.py --partner org_3 quota.check

--partner signs with QUOTA_GATE_PARTNER_SECRET (required, there is no default) and uses
QUOTA_GATE_PARTNER_ISSUER (default https://partner.example).
"""
import os
import sys
import time

import jwt

args = sys.argv[1:]
partner = "--partner" in args
args = [a for a in args if a != "--partner"]

tenant = args[0] if args else ("org_3" if partner else "org_1")
scopes = args[1:] or ["quota.admin"]

if partner:
    issuer = os.environ.get("QUOTA_GATE_PARTNER_ISSUER", "https://partner.example")
    secret = os.environ.get("QUOTA_GATE_PARTNER_SECRET")
    if not secret:
        sys.exit("set QUOTA_GATE_PARTNER_SECRET to mint partner tokens")
else:
    issuer = os.environ.get("QUOTA_GATE_ISSUER", "https://idp.example.test")
    secret = os.environ.get("QUOTA_GATE_JWT_SECRET", "dev-secret-change-me")

claims = {
    "iss": issuer,
    "aud": "api://quota-gate",
    "exp": int(time.time()) + 3600,
    "sub": f"dev-{tenant}",
    "tid": tenant,
    "scp": scopes,
}
print(jwt.encode(claims, secret, algorithm="HS256"))
