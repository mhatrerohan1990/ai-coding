from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Balance:
    """A member's net position in a group; positive means they are owed money."""

    user_id: str
    name: Optional[str]
    balance: float
