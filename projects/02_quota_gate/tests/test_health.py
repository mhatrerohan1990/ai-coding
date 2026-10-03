def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
