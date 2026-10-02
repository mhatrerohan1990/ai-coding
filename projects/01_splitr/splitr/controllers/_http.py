from flask import request

from ..errors import ValidationError


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
