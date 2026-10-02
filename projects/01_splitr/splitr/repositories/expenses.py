from dataclasses import replace

from ..db import get_conn
from ..models import Expense

# API sort name -> column. Only these names ever reach the SQL.
SORT_COLUMNS = {
    "id": "id",
    "amount": "amount_cents",
    "description": "description",
    "created_at": "created_at",
}
SORTABLE_COLUMNS = tuple(SORT_COLUMNS)


def insert(expense) -> Expense:
    """Save an expense row and return it with its generated id."""
    cur = get_conn().execute(
        "INSERT INTO expenses (group_id, paid_by, amount_cents, description, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            expense.group_id,
            expense.paid_by,
            expense.amount_cents,
            expense.description,
            expense.created_at,
        ),
    )
    return replace(expense, id=cur.lastrowid)


def insert_shares(shares):
    """Save a list of ``Share`` rows."""
    get_conn().executemany(
        "INSERT INTO shares (expense_id, user_id, amount_cents) VALUES (?, ?, ?)",
        [(s.expense_id, s.user_id, s.amount_cents) for s in shares],
    )


def list_for_group(group_id, limit, offset, sort):
    """Return a page of a group's expenses, ordered by ``sort`` descending.

    Ties are broken by ``id`` so pagination is stable.

    Raises:
        ValueError: If ``sort`` is not in ``SORTABLE_COLUMNS`` (its column is
            interpolated into the SQL, so it must never come from the caller unchecked).
    """
    if sort not in SORT_COLUMNS:
        raise ValueError("unsupported sort column: %r" % (sort,))
    rows = get_conn().execute(
        "SELECT id, group_id, paid_by, amount_cents, description, created_at FROM expenses "
        "WHERE group_id = ? ORDER BY %s DESC, id DESC LIMIT ? OFFSET ?" % SORT_COLUMNS[sort],
        (group_id, limit, offset),
    ).fetchall()
    return [Expense(**dict(r)) for r in rows]


def paid_amounts(group_id):
    """Return ``[(payer_user_id, cents), ...]`` for every expense in the group."""
    rows = get_conn().execute(
        "SELECT paid_by, amount_cents FROM expenses WHERE group_id = ?", (group_id,)
    ).fetchall()
    return [(r["paid_by"], r["amount_cents"]) for r in rows]


def share_amounts(group_id):
    """Return ``[(user_id, cents), ...]`` for every share of the group's expenses."""
    rows = get_conn().execute(
        "SELECT s.user_id, s.amount_cents FROM shares s "
        "JOIN expenses e ON e.id = s.expense_id WHERE e.group_id = ?",
        (group_id,),
    ).fetchall()
    return [(r["user_id"], r["amount_cents"]) for r in rows]
