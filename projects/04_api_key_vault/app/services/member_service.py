import base64
import binascii
import hashlib
import hmac
import json
import sqlite3

from app.services.admin_service import BadRequestError, NotFoundError

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _encode_cursor(name: str, key_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([name, key_id]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:  # (name, key_id)
    try:
        name, key_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(name, str) or not isinstance(key_id, str):
            raise ValueError
        return name, key_id
    except (binascii.Error, ValueError, TypeError, UnicodeError):
        raise BadRequestError("invalid cursor")


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

    def list_keys(self, tenant_id: str, limit: str | None, cursor: str | None) -> dict:
        if limit is None:
            n = DEFAULT_LIMIT
        else:
            try:
                n = int(limit)
            except ValueError:
                raise BadRequestError("invalid limit")
            if not 1 <= n <= MAX_LIMIT:
                raise BadRequestError("limit out of range")
        after = _decode_cursor(cursor) if cursor is not None else None
        if self.db.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone() is None:
            raise NotFoundError("tenant not found")
        sql = "SELECT key_id, name, prefix, status FROM keys WHERE tenant_id = ?"
        args: list = [tenant_id]
        if after is not None:
            sql += " AND (name, key_id) > (?, ?)"
            args += list(after)
        sql += " ORDER BY name, key_id LIMIT ?"
        args.append(n + 1)  # one extra row tells us whether another page exists
        rows = self.db.execute(sql, args).fetchall()
        page = rows[:n]
        next_cursor = _encode_cursor(page[-1]["name"], page[-1]["key_id"]) if len(rows) > n else None
        return {
            "items": [
                {"key_id": r["key_id"], "name": r["name"], "prefix": r["prefix"], "status": r["status"]}
                for r in page
            ],
            "next_cursor": next_cursor,
        }
