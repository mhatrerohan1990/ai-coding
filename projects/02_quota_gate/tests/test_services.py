"""The service layer is usable without Flask or HTTP."""
import pytest

from conftest import FakeClock
from quota_gate.errors import NotFound
from quota_gate.buckets import BucketStore
from quota_gate.repository import SqlitePolicyRepository
from quota_gate.services import CheckService, PolicyService

BODY = {"match": {"subject": "*", "action": "a"}, "limit": 60, "window_seconds": 60, "burst": 10}


@pytest.fixture
def buckets():
    return BucketStore()


@pytest.fixture
def policies(tmp_path, buckets):
    return PolicyService(SqlitePolicyRepository(str(tmp_path / "svc.db")), buckets)


def test_policy_service_put_get_delete(policies):
    svc = policies

    policy, created = svc.put("org_1", "p", BODY)
    assert created is True
    assert svc.get("org_1", "p") == policy

    _, created = svc.put("org_1", "p", BODY)
    assert created is False

    svc.delete("org_1", "p")
    with pytest.raises(NotFound):
        svc.get("org_1", "p")


def test_delete_missing_policy_raises_not_found(policies):
    with pytest.raises(NotFound):
        policies.delete("org_1", "nope")


def test_matching_is_scoped_to_tenant_subject_and_action(policies):
    svc = policies
    svc.put("org_1", "mine", BODY)
    svc.put("org_2", "theirs", BODY)
    svc.put("org_1", "other-action", {**BODY, "match": {"subject": "*", "action": "b"}})

    ids = [p["policy_id"] for p in svc.matching("org_1", "u", "a")]

    assert ids == ["mine"]


def test_check_service_returns_result_for_fresh_bucket(policies, buckets):
    policies.put("org_1", "p", BODY)

    result = CheckService(policies, FakeClock(1000.0), buckets).check("org_1", "u", "a", cost=3)

    assert (result.allow, result.remaining, result.reset_at, result.limit) == (True, 7, 1003, 60)
    assert result.matched_policies == ["p"]
