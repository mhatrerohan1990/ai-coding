import time

import jwt
import pytest

from tests.helpers import SECRET, as_, bearer, mint

CREATE = ("post", "/tenants/t1/invites", {"json": {"email": "a@x.com"}})
LIST = ("get", "/tenants/t1/members", {})


def call(client, spec, headers=None):
    method, url, kw = spec
    return getattr(client, method)(url, headers=headers or {}, **kw)


def unsigned(tid="t1", role="admin"):
    claims = {"sub": "u", "tid": tid, "role": role, "aud": "api://invites", "exp": int(time.time()) + 60}
    return jwt.encode(claims, key=None, algorithm="none")


BAD_TOKENS = {
    "garbage": "not-a-jwt",
    "wrong_secret": mint(secret="another-secret-another-secret-another-0123"),
    "expired": mint(exp=int(time.time()) - 10),
    "wrong_aud": mint(aud="api://other"),
    "aud_spa": mint(aud="spa"),
    "aud_list_without_ours": mint(aud=["spa", "api://other"]),
    "aud_empty_list": mint(aud=[]),
    "aud_prefix_only": mint(aud="api://invites/extra"),
    "missing_aud": mint(omit=["aud"]),
    "missing_exp": mint(omit=["exp"]),
    "missing_tid": mint(omit=["tid"]),
    "missing_role": mint(omit=["role"]),
    "missing_sub": mint(omit=["sub"]),
    "alg_none": unsigned(),
    "other_hs_alg": mint(alg="HS512"),
}


@pytest.mark.parametrize("spec", [CREATE, LIST], ids=["create", "list"])
class TestAuthn:
    def test_no_header_is_401(self, client, spec):
        resp = call(client, spec)
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"

    def test_non_bearer_scheme_is_401(self, client, spec):
        assert call(client, spec, {"Authorization": f"Basic {mint()}"}).status_code == 401

    @pytest.mark.parametrize("name", BAD_TOKENS)
    def test_bad_token_is_401(self, client, spec, name):
        assert call(client, spec, bearer(BAD_TOKENS[name])).status_code == 401


@pytest.mark.parametrize("spec", [CREATE, LIST], ids=["create", "list"])
def test_tid_must_match_path_tenant(client, spec):
    for role in ("admin", "member"):
        assert call(client, spec, as_("t2", role)).status_code == 403


def test_admin_of_org_1_cannot_create_invite_for_org_2(client, db):
    from sqlalchemy import select

    from app.models import Invite

    resp = client.post(
        "/tenants/org_2/invites", json={"email": "a@x.com"}, headers=as_("org_1", "admin")
    )
    assert resp.status_code == 403
    assert db.scalars(select(Invite)).all() == []
    # ...and the reverse direction.
    resp = client.post(
        "/tenants/org_1/invites", json={"email": "a@x.com"}, headers=as_("org_2", "admin")
    )
    assert resp.status_code == 403
    assert db.scalars(select(Invite)).all() == []


def test_expired_jwt_cannot_create_invite(client, db):
    from sqlalchemy import select

    from app.models import Invite

    expired = bearer(mint("t1", "admin", exp=int(time.time()) - 10))
    resp = client.post("/tenants/t1/invites", json={"email": "a@x.com"}, headers=expired)
    assert resp.status_code == 401
    assert db.scalars(select(Invite)).all() == []


def test_tid_match_is_exact(client):
    for tid in ("T1", "t1 ", "t10", ""):
        assert call(client, LIST, bearer(mint(tid))).status_code in (401, 403)


class TestCreateInviteAuthz:
    def test_admin_of_tenant_allowed(self, client):
        assert call(client, CREATE, as_("t1", "admin")).status_code == 201

    def test_member_forbidden(self, client):
        assert call(client, CREATE, as_("t1", "member")).status_code == 403

    def test_unknown_role_forbidden(self, client):
        assert call(client, CREATE, as_("t1", "superuser")).status_code == 403

    def test_forbidden_creates_nothing(self, client, db):
        from sqlalchemy import select

        from app.models import Invite

        call(client, CREATE, as_("t1", "member"))
        call(client, CREATE, as_("t2", "admin"))
        assert db.scalars(select(Invite)).all() == []

    def test_authn_checked_before_body_validation(self, client):
        resp = client.post("/tenants/t1/invites", json={"email": "bad"})
        assert resp.status_code == 401


class TestListMembersAuthz:
    @pytest.mark.parametrize("role", ["admin", "member"])
    def test_member_or_admin_of_tenant_allowed(self, client, role):
        assert call(client, LIST, as_("t1", role)).status_code == 200

    def test_unknown_role_forbidden(self, client):
        assert call(client, LIST, as_("t1", "guest")).status_code == 403

    def test_does_not_leak_other_tenant(self, client):
        assert call(client, ("get", "/tenants/t2/members", {}), as_("t1", "admin")).status_code == 403


@pytest.mark.parametrize("spec", [CREATE, LIST], ids=["create", "list"])
def test_aud_list_containing_ours_is_accepted(client, spec):
    # RFC 7519 allows aud to be a list; it is valid if it includes api://invites.
    assert call(client, spec, bearer(mint(aud=["spa", "api://invites"]))).status_code in (200, 201)


def test_accept_needs_no_auth(client):
    token = call(client, CREATE, as_("t1", "admin")).json()["token"]
    assert client.post("/invites/accept", json={"token": token}).status_code == 201


def test_accept_ignores_a_bad_bearer_header(client):
    token = call(client, CREATE, as_("t1", "admin")).json()["token"]
    resp = client.post("/invites/accept", json={"token": token}, headers=bearer("garbage"))
    assert resp.status_code == 201


def test_health_is_open(client):
    assert client.get("/health").status_code == 200


def test_missing_secret_fails_loudly(client, monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(RuntimeError):
        call(client, LIST, bearer(mint()))


def test_secret_constant_matches_helper():
    assert jwt.decode(mint(), SECRET, algorithms=["HS256"], audience="api://invites")["tid"] == "t1"
