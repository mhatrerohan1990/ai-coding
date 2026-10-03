import json
import sqlite3

from quota_gate.repository import FIND_MATCHING_SQL, SqlitePolicyRepository

POLICY = {
    "policy_id": "p",
    "tenant_id": "org_1",
    "match": {"subject": "*", "action": "a"},
    "limit": 60,
    "window_seconds": 60,
    "burst": 10,
}


def repo_at(tmp_path):
    return SqlitePolicyRepository(str(tmp_path / "repo.db"))


def test_put_reports_created_then_replaced(tmp_path):
    repo = repo_at(tmp_path)

    assert repo.put(POLICY) is True
    assert repo.put({**POLICY, "limit": 5}) is False
    assert repo.get("org_1", "p")["limit"] == 5


def test_get_returns_none_when_missing(tmp_path):
    assert repo_at(tmp_path).get("org_1", "nope") is None


def test_get_round_trips_the_full_policy(tmp_path):
    repo = repo_at(tmp_path)
    repo.put(POLICY)

    assert repo.get("org_1", "p") == POLICY


def test_delete_reports_whether_anything_was_removed(tmp_path):
    repo = repo_at(tmp_path)
    repo.put(POLICY)

    assert repo.delete("org_1", "p") is True
    assert repo.delete("org_1", "p") is False
    assert repo.get("org_1", "p") is None


def test_list_for_tenant_only_returns_that_tenants_policies(tmp_path):
    repo = repo_at(tmp_path)
    repo.put(POLICY)
    repo.put({**POLICY, "policy_id": "q"})
    repo.put({**POLICY, "tenant_id": "org_2", "policy_id": "z"})

    ids = sorted(p["policy_id"] for p in repo.list_for_tenant("org_1"))

    assert ids == ["p", "q"]


def test_same_policy_id_in_two_tenants_does_not_collide(tmp_path):
    repo = repo_at(tmp_path)
    repo.put({**POLICY, "limit": 1})
    repo.put({**POLICY, "tenant_id": "org_2", "limit": 2})

    assert repo.get("org_1", "p")["limit"] == 1
    assert repo.get("org_2", "p")["limit"] == 2


def test_policies_survive_reopening_the_database(tmp_path):
    repo_at(tmp_path).put(POLICY)

    assert repo_at(tmp_path).get("org_1", "p") == POLICY


# --- match lookup: indexed, tenant-partitioned ------------------------------


def policy(tenant="org_1", policy_id="p", subject="*", action="*"):
    return {**POLICY, "tenant_id": tenant, "policy_id": policy_id,
            "match": {"subject": subject, "action": action}}


def ids(policies):
    return sorted(p["policy_id"] for p in policies)


def test_find_matching_returns_exact_and_wildcard_matches_only(tmp_path):
    repo = repo_at(tmp_path)
    repo.put(policy(policy_id="exact-exact", subject="user_9", action="users.export"))
    repo.put(policy(policy_id="exact-any", subject="user_9", action="*"))
    repo.put(policy(policy_id="any-exact", subject="*", action="users.export"))
    repo.put(policy(policy_id="any-any", subject="*", action="*"))
    repo.put(policy(policy_id="other-user", subject="user_1", action="users.export"))
    repo.put(policy(policy_id="other-action", subject="user_9", action="api.read"))

    found = repo.find_matching("org_1", "user_9", "users.export")

    assert ids(found) == ["any-any", "any-exact", "exact-any", "exact-exact"]


def test_find_matching_is_scoped_to_the_tenant(tmp_path):
    repo = repo_at(tmp_path)
    repo.put(policy(tenant="org_1", policy_id="mine"))
    repo.put(policy(tenant="org_2", policy_id="theirs"))

    assert ids(repo.find_matching("org_1", "u", "a")) == ["mine"]


def test_replacing_a_policy_updates_what_it_matches(tmp_path):
    repo = repo_at(tmp_path)
    repo.put(policy(policy_id="p", action="a"))
    repo.put(policy(policy_id="p", action="b"))

    assert repo.find_matching("org_1", "u", "a") == []
    assert ids(repo.find_matching("org_1", "u", "b")) == ["p"]


def test_deleted_policy_is_not_matched(tmp_path):
    repo = repo_at(tmp_path)
    repo.put(policy(policy_id="p"))
    repo.delete("org_1", "p")

    assert repo.find_matching("org_1", "u", "a") == []


def test_find_matching_uses_an_index_search_not_a_scan(tmp_path):
    repo = repo_at(tmp_path)
    with sqlite3.connect(str(tmp_path / "repo.db")) as db:
        plan = db.execute(
            "EXPLAIN QUERY PLAN " + FIND_MATCHING_SQL, ("org_1", "u", "a")
        ).fetchall()

    detail = " ".join(row[3] for row in plan)
    assert "SEARCH" in detail and "USING" in detail and "INDEX" in detail
    assert "SCAN" not in detail
    assert "tenant_id=?" in detail


def test_database_created_by_the_old_schema_is_migrated(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE policies (
                   tenant_id TEXT NOT NULL, policy_id TEXT NOT NULL, body TEXT NOT NULL,
                   PRIMARY KEY (tenant_id, policy_id))"""
        )
        legacy = policy(policy_id="old", subject="user_9", action="users.export")
        db.execute("INSERT INTO policies VALUES (?, ?, ?)", ("org_1", "old", json.dumps(legacy)))

    repo = SqlitePolicyRepository(path)

    assert ids(repo.find_matching("org_1", "user_9", "users.export")) == ["old"]
    assert repo.find_matching("org_1", "user_1", "users.export") == []
