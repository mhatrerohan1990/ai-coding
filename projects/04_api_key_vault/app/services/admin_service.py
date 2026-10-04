import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone

KEY_PREFIX = "gk_live_"


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class AdminService:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def _require_tenant(self, tenant_id: str) -> None:
        row = self.db.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        if row is None:
            raise NotFoundError("tenant not found")

    def _require_key(self, tenant_id: str, key_id: str) -> sqlite3.Row:
        self._require_tenant(tenant_id)
        row = self.db.execute(
            "SELECT * FROM keys WHERE key_id = ? AND tenant_id = ?", (key_id, tenant_id)
        ).fetchone()
        if row is None:
            raise NotFoundError("key not found")
        return row

    def create_key(self, tenant_id: str, name: str, created_by: str) -> dict:
        self._require_tenant(tenant_id)
        key_id = "key_" + secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)  # 256 bits
        created_at = datetime.now(timezone.utc).isoformat()
        while True:
            prefix = KEY_PREFIX + secrets.token_hex(2)
            try:
                self.db.execute(
                    "INSERT INTO keys (key_id, tenant_id, name, prefix, secret_hash, created_by, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (key_id, tenant_id, name, prefix, _hash(secret), created_by, created_at),
                )
                break
            except sqlite3.IntegrityError:
                self.db.rollback()  # prefix collision, retry
        self.db.commit()
        return {"key_id": key_id, "secret": f"{prefix}.{secret}", "prefix": prefix}

    def revoke_key(self, tenant_id: str, key_id: str) -> None:
        self._require_key(tenant_id, key_id)
        self.db.execute("UPDATE keys SET status = 'REVOKED' WHERE key_id = ?", (key_id,))
        self.db.commit()

    def rotate_key(self, tenant_id: str, key_id: str) -> dict:
        row = self._require_key(tenant_id, key_id)
        # Claim: only one caller can move ACTIVE -> ROTATING. Everyone else is rejected.
        claim = self.db.execute(
            "UPDATE keys SET status = 'ROTATING' "
            "WHERE key_id = ? AND tenant_id = ? AND status = 'ACTIVE'",
            (key_id, tenant_id),
        )
        self.db.commit()
        if claim.rowcount == 0:
            raise ConflictError("key is not active")
        secret = secrets.token_urlsafe(32)
        # Finish: only if we still own the rotation (a revoke in between turns it REVOKED).
        done = self.db.execute(
            "UPDATE keys SET secret_hash = ?, status = 'ACTIVE' "
            "WHERE key_id = ? AND status = 'ROTATING'",
            (_hash(secret), key_id),
        )
        self.db.commit()
        if done.rowcount == 0:
            raise ConflictError("key was revoked during rotation")
        return {"key_id": key_id, "secret": f"{row['prefix']}.{secret}"}
