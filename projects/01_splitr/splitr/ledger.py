from datetime import datetime

from . import notifier
from .db import get_conn


def create_group(name, members):
    conn = get_conn()
    cur = conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
    group_id = cur.lastrowid
    for m in members:
        conn.execute(
            "INSERT INTO members (group_id, name, email) VALUES (?, ?, ?)",
            (group_id, m["name"], m.get("email")),
        )
    conn.commit()
    return group_id


def get_members(group_id):
    rows = get_conn().execute(
        "SELECT name, email FROM members WHERE group_id = ?", (group_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def split_evenly(amount, people):
    share = round(amount / len(people), 2)
    return {p: share for p in people}


def add_expense(group_id, paid_by, amount, description="", split_among=[]):
    members = get_members(group_id)
    if not split_among:
        split_among.extend(m["name"] for m in members)

    shares = split_evenly(amount, split_among)

    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO expenses (group_id, paid_by, amount, description, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (group_id, paid_by, amount, description, datetime.now().isoformat()),
    )
    expense_id = cur.lastrowid
    for member, share in shares.items():
        conn.execute(
            "INSERT INTO shares (expense_id, member, amount) VALUES (?, ?, ?)",
            (expense_id, member, share),
        )

    notifier.notify_expense(members, paid_by, amount, description, shares)
    conn.commit()
    return expense_id, shares


def list_expenses(group_id, page=1, limit=20, sort="created_at"):
    offset = page * limit
    rows = get_conn().execute(
        f"SELECT id, paid_by, amount, description, created_at FROM expenses "
        f"WHERE group_id = ? ORDER BY {sort} DESC LIMIT ? OFFSET ?",
        (group_id, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def record_settlement(group_id, from_member, to_member, amount):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO settlements (group_id, from_member, to_member, amount, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (group_id, from_member, to_member, amount, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def balances(group_id):
    """Net balance per member. Positive = the group owes them money."""
    conn = get_conn()
    bal = {m["name"]: 0.0 for m in get_members(group_id)}

    for e in conn.execute(
        "SELECT paid_by, amount FROM expenses WHERE group_id = ?", (group_id,)
    ):
        bal[e["paid_by"]] = bal.get(e["paid_by"], 0.0) + e["amount"]

    for s in conn.execute(
        "SELECT s.member, s.amount FROM shares s "
        "JOIN expenses e ON e.id = s.expense_id WHERE e.group_id = ?",
        (group_id,),
    ):
        bal[s["member"]] = bal.get(s["member"], 0.0) - s["amount"]

    for st in conn.execute(
        "SELECT from_member, to_member, amount FROM settlements WHERE group_id = ?",
        (group_id,),
    ):
        bal[st["from_member"]] = bal.get(st["from_member"], 0.0) - st["amount"]
        bal[st["to_member"]] = bal.get(st["to_member"], 0.0) + st["amount"]

    return {name: round(v, 2) for name, v in bal.items()}
