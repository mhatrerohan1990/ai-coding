import re
from dataclasses import dataclass

from quota_gate.errors import InvalidRequest

POLICY_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
MAX_WINDOW_SECONDS = 86400

POLICY_FIELDS = {"match", "limit", "window_seconds", "burst"}
MATCH_FIELDS = {"subject", "action"}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)  # True is not a count


def _non_empty_str(value):
    return isinstance(value, str) and value != ""


def require_object(body):
    if not isinstance(body, dict):
        raise InvalidRequest("request body must be a JSON object")
    return body


def validate_policy_id(policy_id):
    if not POLICY_ID_RE.fullmatch(policy_id):
        raise InvalidRequest("policy_id must match ^[a-z0-9][a-z0-9_-]{0,63}$")


def parse_policy_body(body):
    """Return the policy fields to store, or raise InvalidRequest.

    Strict: unknown fields are rejected, so a body can never smuggle in
    tenant_id / policy_id or junk that would later be echoed back.
    """
    body = require_object(body)
    unknown = sorted(set(body) - POLICY_FIELDS)
    if unknown:
        raise InvalidRequest(f"unknown field(s): {', '.join(unknown)}")

    match = body.get("match")
    if not isinstance(match, dict) or set(match) != MATCH_FIELDS:
        raise InvalidRequest("match must be an object with exactly 'subject' and 'action'")
    for field in sorted(MATCH_FIELDS):
        if not _non_empty_str(match[field]):
            raise InvalidRequest(f"match.{field} must be a non-empty string ('*' for any)")

    for field in ("limit", "burst"):
        if not _is_int(body.get(field)) or body[field] < 1:
            raise InvalidRequest(f"{field} must be an integer >= 1")
    window = body.get("window_seconds")
    if not _is_int(window) or not 1 <= window <= MAX_WINDOW_SECONDS:
        raise InvalidRequest(f"window_seconds must be an integer between 1 and {MAX_WINDOW_SECONDS}")

    return {
        "match": {"subject": match["subject"], "action": match["action"]},
        "limit": body["limit"],
        "window_seconds": window,
        "burst": body["burst"],
    }


@dataclass(frozen=True)
class CheckRequest:
    tenant_id: str
    subject: str
    action: str
    cost: int = 1

    @classmethod
    def parse(cls, body):
        """Unknown fields are ignored: callers on the hot path may add their own."""
        body = require_object(body)
        for field in ("tenant_id", "subject", "action"):
            if not _non_empty_str(body.get(field)):
                raise InvalidRequest(f"{field} must be a non-empty string")
        cost = body.get("cost", 1)  # an explicit null is invalid, not "default"
        if not _is_int(cost) or cost < 1:
            raise InvalidRequest("cost must be an integer >= 1")
        return cls(body["tenant_id"], body["subject"], body["action"], cost)
