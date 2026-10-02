class ValidationError(ValueError):
    """The request data is invalid; the API maps this to HTTP 400."""


class NotFound(LookupError):
    """A referenced resource does not exist; the API maps this to HTTP 404."""


class GroupNotFound(NotFound):
    """The group id does not exist."""


class UserNotFound(NotFound):
    """The user id does not exist."""
