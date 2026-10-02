from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Payment:
    """A suggested transfer that moves a group closer to being settled up."""

    from_user_id: str
    from_name: Optional[str]
    to_user_id: str
    to_name: Optional[str]
    amount: float
