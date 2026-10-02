from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Settlement:
    """A payment from one member to another that reduces what is owed."""

    id: Optional[int]
    group_id: int
    from_user_id: str
    to_user_id: str
    amount: float
    created_at: str
