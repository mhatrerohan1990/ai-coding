import json
import sqlite3
from contextlib import closing
from typing import Optional, Protocol


# Candidates for a check: the tenant's policies whose match is the request's value
# or "*", per field. Served by idx_policies_match, never a table scan.
FIND_MATCHING_SQL = """
    SELECT body FROM policies
    WHERE tenant_id = ?
      AND match_subject IN (?2, '*')
      AND match_action IN (?3, '*')
    ORDER BY policy_id
"""


class PolicyRepository(Protocol):
    """Storage for policies. Every access is partitioned by tenant:

    get/put/delete by (tenant_id, policy_id), list/find by tenant_id. Maps onto
    DynamoDB as partition key = tenant_id, sort key = policy_id, with a secondary
    index on (tenant_id, match_subject, match_action) for find_matching.
    """

    def put(self, policy: dict) -> bool:
        """Upsert. Returns True if created, False if an existing policy was replaced."""

    def get(self, tenant_id: str, policy_id: str) -> Optional[dict]: ...

    def delete(self, tenant_id: str, policy_id: str) -> bool:
        """Returns True if a policy was removed."""

    def list_for_tenant(self, tenant_id: str) -> list: ...

    def find_matching(self, tenant_id: str, subject: str, action: str) -> list:
        """Policies of the tenant whose match.subject/action equal the values or are '*'."""


class SqlitePolicyRepository:
    def __init__(self, db_path):
        self._db_path = db_path
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS policies (
                       tenant_id     TEXT NOT NULL,
                       policy_id     TEXT NOT NULL,
                       match_subject TEXT NOT NULL,
                       match_action  TEXT NOT NULL,
                       body          TEXT NOT NULL,
                       PRIMARY KEY (tenant_id, policy_id)
                   )"""
            )
            self._migrate_legacy_schema(db)
            db.execute(
                """CREATE INDEX IF NOT EXISTS idx_policies_match
                   ON policies (tenant_id, match_subject, match_action)"""
            )

    @staticmethod
    def _migrate_legacy_schema(db):
        """Databases created before match columns existed: add them, backfill from body."""
        columns = {row[1] for row in db.execute("PRAGMA table_info(policies)")}
        if "match_subject" in columns:
            return
        db.execute("ALTER TABLE policies ADD COLUMN match_subject TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE policies ADD COLUMN match_action TEXT NOT NULL DEFAULT ''")
        db.execute(
            """UPDATE policies SET
                   match_subject = json_extract(body, '$.match.subject'),
                   match_action  = json_extract(body, '$.match.action')"""
        )

    def _connect(self):
        # One short-lived connection per call: safe under Flask's threaded server.
        # `with conn` commits/rolls back; closing() releases the file handle.
        db = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        return _Transaction(db)

    def put(self, policy):
        with self._connect() as db:
            exists = db.execute(
                "SELECT 1 FROM policies WHERE tenant_id = ? AND policy_id = ?",
                (policy["tenant_id"], policy["policy_id"]),
            ).fetchone()
            db.execute(
                """INSERT OR REPLACE INTO policies
                       (tenant_id, policy_id, match_subject, match_action, body)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    policy["tenant_id"],
                    policy["policy_id"],
                    policy["match"]["subject"],
                    policy["match"]["action"],
                    json.dumps(policy),
                ),
            )
        return exists is None

    def get(self, tenant_id, policy_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT body FROM policies WHERE tenant_id = ? AND policy_id = ?",
                (tenant_id, policy_id),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, tenant_id, policy_id):
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM policies WHERE tenant_id = ? AND policy_id = ?",
                (tenant_id, policy_id),
            )
        return cursor.rowcount > 0

    def list_for_tenant(self, tenant_id):
        with self._connect() as db:
            rows = db.execute(
                "SELECT body FROM policies WHERE tenant_id = ? ORDER BY policy_id",
                (tenant_id,),
            ).fetchall()
        return [json.loads(body) for (body,) in rows]

    def find_matching(self, tenant_id, subject, action):
        with self._connect() as db:
            rows = db.execute(FIND_MATCHING_SQL, (tenant_id, subject, action)).fetchall()
        return [json.loads(body) for (body,) in rows]


class _Transaction:
    """BEGIN IMMEDIATE ... COMMIT/ROLLBACK, then close. Serializes writers."""

    def __init__(self, db):
        self._db = db

    def __enter__(self):
        self._db.execute("BEGIN IMMEDIATE")
        return self._db

    def __exit__(self, exc_type, exc, tb):
        with closing(self._db):
            self._db.execute("ROLLBACK" if exc_type else "COMMIT")
        return False
