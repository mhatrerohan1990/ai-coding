"""Seed tenants t1 and t2 with one admin and one member each (uids u-<role>-<tid>).

    python scripts/seed.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.db as db  # noqa: E402

conn = sqlite3.connect(db.DB_PATH)
db.init_db(conn)
for tid in ("t1", "t2"):
    conn.execute("INSERT OR IGNORE INTO tenants VALUES (?, ?)", (tid, f"Tenant {tid[1:]}"))
    for role in ("admin", "member"):
        conn.execute(
            "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)",
            (f"u-{role}-{tid}", tid, f"{role.title()} {tid}", role),
        )
conn.commit()
print(f"seeded {db.DB_PATH}")
