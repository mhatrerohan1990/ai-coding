from conftest import ISSUER, SECRET, bearer, mint_token
from quota_gate.app import create_app

BODY = {"match": {"subject": "*", "action": "a"}, "limit": 60, "window_seconds": 60, "burst": 10}
URL = "/v1/tenants/org_1/policies/p"


def test_policy_survives_an_app_restart(tmp_path):
    db = str(tmp_path / "restart.db")
    admin = bearer(mint_token())
    create_app(db, SECRET, ISSUER).test_client().put(URL, json=BODY, headers=admin)

    restarted = create_app(db, SECRET, ISSUER).test_client()

    res = restarted.get(URL, headers=admin)
    assert res.status_code == 200
    assert res.get_json() == {"policy_id": "p", "tenant_id": "org_1", **BODY}


def test_delete_survives_an_app_restart(tmp_path):
    db = str(tmp_path / "restart.db")
    admin = bearer(mint_token())
    first = create_app(db, SECRET, ISSUER).test_client()
    first.put(URL, json=BODY, headers=admin)
    first.delete(URL, headers=admin)

    restarted = create_app(db, SECRET, ISSUER).test_client()

    assert restarted.get(URL, headers=admin).status_code == 404
