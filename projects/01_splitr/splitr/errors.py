class ValidationError(ValueError):
    """The request data is invalid; the API maps this to HTTP 400."""


class NotFound(LookupError):
    """A referenced resource does not exist; the API maps this to HTTP 404."""


class GroupNotFound(NotFound):
    """The group id does not exist."""


class UserNotFound(NotFound):
    """The user id does not exist."""


class Conflict(Exception):
    """The request clashes with an earlier one (e.g. a reused idempotency key); maps to HTTP 409."""
