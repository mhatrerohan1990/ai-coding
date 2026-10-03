import time

from flask import Flask, jsonify, request

from quota_gate.auth import (
    ADMIN_SCOPE,
    CHECK_SCOPE,
    TokenVerifier,
    requires_scope,
    tenant_from_body,
)
from quota_gate.buckets import BucketStore
from quota_gate.errors import register_error_handlers
from quota_gate.repository import SqlitePolicyRepository
from quota_gate.validation import CheckRequest
from quota_gate.services import CheckService, PolicyService


def create_app(db_path, jwt_secret, issuer, clock=time.time, buckets=None):
    app = Flask(__name__)
    register_error_handlers(app)
    verifier = TokenVerifier(jwt_secret, issuer)
    admin_only = requires_scope(verifier, ADMIN_SCOPE)
    check_only = requires_scope(verifier, CHECK_SCOPE, tenant_from=tenant_from_body)
    buckets = BucketStore() if buckets is None else buckets
    policies = PolicyService(SqlitePolicyRepository(db_path), buckets)
    checks = CheckService(policies, clock, buckets)

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.put("/v1/tenants/<tenant_id>/policies/<policy_id>")
    @admin_only
    def put_policy(tenant_id, policy_id):
        policy, created = policies.put(tenant_id, policy_id, request.get_json(silent=True))
        return jsonify(policy), 201 if created else 200

    @app.get("/v1/tenants/<tenant_id>/policies/<policy_id>")
    @admin_only
    def get_policy(tenant_id, policy_id):
        return jsonify(policies.get(tenant_id, policy_id))

    @app.delete("/v1/tenants/<tenant_id>/policies/<policy_id>")
    @admin_only
    def delete_policy(tenant_id, policy_id):
        policies.delete(tenant_id, policy_id)
        return "", 204

    @app.post("/v1/check")
    @check_only
    def check():
        req = CheckRequest.parse(request.get_json(silent=True))
        result = checks.check(req.tenant_id, req.subject, req.action, req.cost)
        response = jsonify(
            allow=result.allow,
            remaining=result.remaining,
            reset_at=result.reset_at,
            matched_policies=result.matched_policies,
        )
        if result.limit is not None:  # no policy applied -> no limit to report
            response.headers["X-RateLimit-Limit"] = str(result.limit)
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        if not result.allow:
            response.status_code = 429
            response.headers["Retry-After"] = str(result.retry_after)
        return response

    return app
