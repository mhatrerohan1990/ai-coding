import hashlib
import hmac
import sqlite3

from app.services.admin_service import NotFoundError


class MemberService:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def introspect(self, raw_key: str) -> dict:
        inactive = {"active": False}
        prefix, sep, secret = raw_key.partition(".")
        if not sep or not secret:
            return inactive
        row = self.db.execute("SELECT * FROM keys WHERE prefix = ?", (prefix,)).fetchone()
        if row is None:
            raise NotFoundError("prefix not found")
        presented = hashlib.sha256(secret.encode()).hexdigest()
        if not hmac.compare_digest(presented, row["secret_hash"]):
            return inactive
        if row["status"] != "ACTIVE":
            return inactive
        return {
            "active": True,
            "tenant_id": row["tenant_id"],
            "key_id": row["key_id"],
            "name": row["name"],
        }

    def list_keys(self, tenant_id: str) -> list[dict]:
        if self.db.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone() is None:
            raise NotFoundError("tenant not found")
        rows = self.db.execute(
            "SELECT key_id, name, prefix, status FROM keys WHERE tenant_id = ?", (tenant_id,)
        ).fetchall()
        return [
            {"key_id": r["key_id"], "name": r["name"], "prefix": r["prefix"], "status": r["status"]}
            for r in rows
        ]
