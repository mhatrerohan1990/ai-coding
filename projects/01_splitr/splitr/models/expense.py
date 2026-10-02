from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Expense:
    """Something one member paid for. ``id`` is ``None`` until it is saved."""

    id: Optional[int]
    group_id: int
    paid_by: str  # user id of the payer
    amount_cents: int
    description: Optional[str]
    created_at: str


@dataclass(frozen=True)
class Share:
    """The part of an expense that one user owes."""

    expense_id: int
    user_id: str
    amount_cents: int
