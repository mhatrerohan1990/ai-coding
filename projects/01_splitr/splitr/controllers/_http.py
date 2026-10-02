import hashlib
import json
from functools import wraps

from flask import jsonify, request

from ..errors import ValidationError
from ..services import idempotency as idempotency_service


def json_body(*required):
    """Return the request's JSON object, checking that it has the ``required`` keys.

    Raises:
        ValidationError: If the body is not a JSON object or a key is missing.
    """
    data = request.get_json()
    if not isinstance(data, dict):
        raise ValidationError("a JSON object is required")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValidationError("missing required field(s): %s" % ", ".join(missing))
    return data


def int_arg(name, default):
    """Read an integer query parameter, or raise ``ValidationError``."""
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValidationError("%s must be an integer" % name)


def _fingerprint():
    """Hash of the request's method, path and canonical JSON body."""
    body = json.dumps(
        request.get_json(silent=True), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(f"{request.method} {request.path}\n{body}".encode()).hexdigest()


def idempotent(view):
    """Make a POST view safe to retry when the client sends an ``Idempotency-Key`` header.

    The view must return ``(payload_dict, status)``. With the header, a repeat of
    the same request returns the original response (marked
    ``Idempotent-Replayed: true``) without doing the work again; reusing the key
    for a different request is a 409. Without the header the view runs normally
    (and a retry can create a duplicate, so clients should send one).
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if key is None:
            payload, status = view(*args, **kwargs)
            return jsonify(payload), status

        def operation():
            payload, status = view(*args, **kwargs)
            return status, payload

        status, payload, replayed = idempotency_service.run_once(
            idempotency_service.validate_key(key), _fingerprint(), operation
        )
        response = jsonify(payload)
        response.status_code = status
        if replayed:
            response.headers["Idempotent-Replayed"] = "true"
        return response

    return wrapper
