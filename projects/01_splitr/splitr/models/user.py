from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class User:
    """A person. ``id`` is a stable UUID; ``name`` and ``email`` may change."""

    id: str
    name: str
    email: Optional[str] = None
