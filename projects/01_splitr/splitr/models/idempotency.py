from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class IdempotencyRecord:
    """The remembered outcome of a request that was sent with an ``Idempotency-Key``."""

    key: str
    fingerprint: str  # hash of method + path + body, to detect a reused key
    status: Optional[int]
    body: Optional[str]  # the JSON response, as text
    created_at: str
