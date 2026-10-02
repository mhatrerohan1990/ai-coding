import pytest

from quota_gate.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"), "test-secret", "https://idp.example.test")
    return app.test_client()


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
