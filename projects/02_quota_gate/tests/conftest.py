import time

import jwt
import pytest

from quota_gate.app import create_app

SECRET = "test-secret-test-secret-test-secret-32b"
ISSUER = "https://idp.example.test"
AUDIENCE = "api://quota-gate"
PARTNER_SECRET = "partner-secret-partner-secret-32bytes!"
PARTNER_ISSUER = "https://partner.example"


def mint_token(secret=SECRET, **overrides):
    """Mint a valid org_1 admin token. Pass claim=None to drop that claim."""
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        "sub": "admin_1",
        "tid": "org_1",
        "scp": ["quota.admin"],
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, secret, algorithm="HS256")


def partner_token(**overrides):
    """A valid token from the partner IdP: its issuer, its secret, tenant org_3."""
    defaults = {"secret": PARTNER_SECRET, "iss": PARTNER_ISSUER, "tid": "org_3", "sub": "partner_admin"}
    return mint_token(**{**defaults, **overrides})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class FakeClock:
    def __init__(self, now=1_727_740_000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def app(tmp_path, clock):
    return create_app(
        str(tmp_path / "test.db"), SECRET, ISSUER, clock=clock,
        partner_secret=PARTNER_SECRET,
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(client):
    """Headers for an org_1 token with quota.admin."""
    return bearer(mint_token())


@pytest.fixture
def svc(client):
    """Headers for an org_1 service token with quota.check only."""
    return bearer(mint_token(sub="svc_1", scp=["quota.check"]))
