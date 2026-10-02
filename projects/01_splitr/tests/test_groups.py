"""Group creation and membership."""

from .helpers import balances_by_name


def test_create_group(client, ids):
    res = client.post("/groups", json={"name": "flat", "members": list(ids.values())})
    assert res.status_code == 201
    assert "id" in res.get_json()


def test_create_group_requires_members(client):
    res = client.post("/groups", json={"name": "flat"})
    assert res.status_code == 400


def test_same_user_can_be_in_several_groups(client, ids):
    g1 = client.post("/groups", json={"name": "one", "members": [ids["alice"], ids["bob"]]})
    g2 = client.post("/groups", json={"name": "two", "members": [ids["alice"], ids["carol"]]})
    g1, g2 = g1.get_json()["id"], g2.get_json()["id"]

    client.post(f"/groups/{g1}/expenses", json={"paid_by": ids["alice"], "amount": 10})
    client.post(f"/groups/{g2}/expenses", json={"paid_by": ids["carol"], "amount": 20})

    assert balances_by_name(client, g1) == {"alice": 5, "bob": -5}
    assert balances_by_name(client, g2) == {"alice": -10, "carol": 10}
