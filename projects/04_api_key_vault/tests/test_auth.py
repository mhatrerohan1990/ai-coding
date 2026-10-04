import pytest

from tests.conftest import auth, token

ADMIN_CALLS = [
    ("post", "/tenants/t1/keys", {"json": {"name": "x"}}, "create"),
    ("post", "/tenants/t1/keys/key_x/revoke", {}, "revoke"),
    ("post", "/tenants/t1/keys/key_x/rotate", {}, "rotate"),
]
LIST_CALL = ("get", "/tenants/t1/keys", {}, "list")


def call(client, spec, headers):
    method, path, kw, _ = spec
    return getattr(client, method)(path, headers=headers, **kw)


@pytest.fixture
def anon(client):
    client.headers.clear()
    return client


@pytest.mark.parametrize("spec", ADMIN_CALLS + [LIST_CALL])
def test_missing_or_malformed_header_is_401(anon, spec):
    assert call(anon, spec, {}).status_code == 401
    assert call(anon, spec, {"Authorization": "Basic abc"}).status_code == 401
    assert call(anon, spec, {"Authorization": "Bearer not-a-jwt"}).status_code == 401


@pytest.mark.parametrize("bad", [
    dict(aud="api://other"),
    dict(secret="wrong-secret"),
    dict(exp=1),
    dict(drop=("aud",)),
    dict(drop=("exp",)),
    dict(drop=("tid",)),
    dict(drop=("role",)),
    dict(role="superuser"),
])
def test_bad_token_is_401(anon, bad):
    assert call(anon, ADMIN_CALLS[0], auth(**bad)).status_code == 401


def test_alg_none_and_other_algorithms_rejected(anon):
    import jwt as pyjwt
    none_tok = pyjwt.encode({"tid": "t1", "role": "admin", "aud": "api://keys", "exp": 9999999999,
                             "scope": "create"}, None, algorithm="none")
    assert call(anon, ADMIN_CALLS[0], {"Authorization": f"Bearer {none_tok}"}).status_code == 401
    assert call(anon, ADMIN_CALLS[0], auth(alg="HS512")).status_code == 401


@pytest.mark.parametrize("spec", ADMIN_CALLS + [LIST_CALL])
def test_tenant_mismatch_is_401(anon, spec):
    assert call(anon, spec, auth(tid="t2")).status_code == 401


@pytest.mark.parametrize("spec", ADMIN_CALLS)
def test_member_cannot_call_admin_endpoints(anon, spec):
    assert call(anon, spec, auth(role="member")).status_code == 403


@pytest.mark.parametrize("spec", ADMIN_CALLS + [LIST_CALL])
def test_missing_scope_is_403(anon, spec):
    assert call(anon, spec, auth(scope="")).status_code == 403
    others = " ".join(s for s in ("create", "revoke", "rotate", "list") if s != spec[3])
    assert call(anon, spec, auth(scope=others)).status_code == 403


def test_admin_with_scope_succeeds_and_member_can_list(anon):
    created = call(anon, ADMIN_CALLS[0], auth(scope="create"))
    assert created.status_code == 200
    assert call(anon, LIST_CALL, auth(role="member", scope="list")).status_code == 200
    assert call(anon, LIST_CALL, auth(role="admin", scope="list")).status_code == 200


def test_introspect_and_health_need_no_token(anon):
    assert anon.get("/health").status_code == 200
    assert anon.post("/keys/introspect", json={"secret": "x.y"}).json() == {"active": False}


def test_app_refuses_to_start_without_secret(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


@pytest.mark.parametrize("bad", [
    dict(drop=("uid",)),                      # uid claim required
    dict(uid="u-ghost"),                      # uid not in users
    dict(uid="u-member-t1"),                  # token says admin, table says member
    dict(role="member", uid="u-admin-t1"),    # token says member, table says admin
    dict(uid="u-admin-t2"),                   # user belongs to t2, token tid is t1
])
def test_user_checks_are_401(anon, bad):
    assert call(anon, ADMIN_CALLS[0], auth(**bad)).status_code == 401
    assert call(anon, LIST_CALL, auth(**{**bad, "scope": "list"})).status_code == 401
