import json
from datetime import timedelta

from .. import clock, db
from ..errors import Conflict, ValidationError
from ..repositories import idempotency as idempotency_repo

KEY_TTL = timedelta(hours=24)
MAX_KEY_LENGTH = 255


def validate_key(key):
    """Return ``key`` if it is a usable idempotency key.

    Raises:
        ValidationError: If it is empty, longer than ``MAX_KEY_LENGTH``, has
            leading/trailing whitespace, or contains non-printable characters.
    """
    if (
        not isinstance(key, str)
        or not key
        or len(key) > MAX_KEY_LENGTH
        or key != key.strip()
        or not key.isprintable()
    ):
        raise ValidationError(
            "Idempotency-Key must be 1-%d printable characters" % MAX_KEY_LENGTH
        )
    return key


def run_once(key, fingerprint, operation):
    """Run ``operation`` at most once for ``key``, replaying the saved result on repeats.

    Everything happens in one transaction: the key is claimed, ``operation`` runs
    and its response is stored, then it all commits together. So a key is only
    ever recorded alongside the writes it covers, a crash cannot leave one
    without the other, and two simultaneous requests with the same key are
    serialized by the database lock (the second one replays the first's result).

    If ``operation`` raises, the transaction rolls back, the key is released and
    nothing is stored: errors are not cached, so a corrected retry can succeed.
    Keys expire after ``KEY_TTL``.

    Args:
        key: The client's idempotency key (already validated).
        fingerprint: Hash of the request (method, path, body). A repeat of the
            key with a different fingerprint is a client bug.
        operation: Zero-argument callable returning ``(status, body_dict)``.

    Returns:
        ``(status, body, replayed)``; ``replayed`` is True when the response
        came from an earlier request rather than from running ``operation``.

    Raises:
        Conflict: If ``key`` was already used for a different request.
    """
    with db.transaction():
        idempotency_repo.purge_before(
            (clock.utc_now() - KEY_TTL).isoformat(timespec="microseconds")
        )
        if not idempotency_repo.claim(key, fingerprint, clock.utc_now_iso()):
            record = idempotency_repo.get(key)
            if record.fingerprint != fingerprint:
                raise Conflict("Idempotency-Key was already used for a different request")
            return record.status, json.loads(record.body), True

        status, body = operation()
        idempotency_repo.save_response(key, status, json.dumps(body))
        return status, body, False
