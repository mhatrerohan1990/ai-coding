import pytest
from flask import Flask

from quota_gate.errors import (
    ApiError,
    Forbidden,
    InvalidRequest,
    InvalidToken,
    NotFound,
    register_error_handlers,
)

URL = "/v1/tenants/org_1/policies/missing"


def test_get_missing_policy_returns_404_in_error_shape(client, admin):
    res = client.get(URL, headers=admin)

    assert res.status_code == 404
    assert res.get_json() == {
        "error": {"code": "not_found", "message": "policy 'missing' not found"}
    }


def test_delete_missing_policy_returns_404_in_error_shape(client, admin):
    res = client.delete(URL, headers=admin)

    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "exc_class, status, code",
    [
        (InvalidRequest, 400, "invalid_request"),
        (InvalidToken, 401, "invalid_token"),
        (Forbidden, 403, "forbidden"),
        (NotFound, 404, "not_found"),
    ],
)
def test_raised_api_errors_render_status_code_and_message(exc_class, status, code):
    app = Flask(__name__)
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise exc_class("something specific")

    res = app.test_client().get("/boom")

    assert res.status_code == status
    assert res.get_json() == {"error": {"code": code, "message": "something specific"}}


def test_api_error_subclasses_share_a_base_class():
    assert issubclass(NotFound, ApiError)


# --- everything is JSON, never an HTML error page ---------------------------


def test_unknown_route_is_404_in_error_shape(client):
    res = client.get("/v1/nope")

    assert res.status_code == 404
    assert res.is_json
    assert res.get_json()["error"]["code"] == "not_found"


def test_wrong_method_is_405_in_error_shape(client):
    res = client.get("/v1/check")

    assert res.status_code == 405
    assert res.is_json
    assert res.get_json()["error"]["code"] == "method_not_allowed"


def test_unexpected_exception_is_500_json_without_leaking_details(app):
    @app.get("/boom")
    def boom():
        return {"x": 1 / 0}

    res = app.test_client().get("/boom")

    assert res.status_code == 500
    assert res.is_json
    body = res.get_json()
    assert body["error"]["code"] == "internal_error"
    assert "division" not in body["error"]["message"]
    assert "ZeroDivision" not in res.get_data(as_text=True)
