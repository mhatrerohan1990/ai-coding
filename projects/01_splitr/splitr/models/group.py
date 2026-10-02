from dataclasses import dataclass


@dataclass(frozen=True)
class Group:
    """A set of users who share expenses (membership lives in ``group_members``)."""

    id: int
    name: str
