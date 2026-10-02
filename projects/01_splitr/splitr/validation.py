"""Input validators shared by the services. They raise ``ValidationError``."""

from .errors import ValidationError


def is_name(value):
    """True for a non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def validate_user_fields(fields):
    """Validate the ``name`` and/or ``email`` entries present in ``fields``."""
    if "name" in fields and not is_name(fields["name"]):
        raise ValidationError("name must be a non-empty string")
    if "email" in fields:
        email = fields["email"]
        if email is not None and not (isinstance(email, str) and "@" in email):
            raise ValidationError("email must be a string containing '@', or null")


def validate_ids(value, field):
    """Require a non-empty list of unique strings (user ids)."""
    if not isinstance(value, list) or not value:
        raise ValidationError("%s must be a non-empty list of user ids" % field)
    if not all(isinstance(v, str) and v for v in value):
        raise ValidationError("%s must contain only user id strings" % field)
    if len(set(value)) != len(value):
        raise ValidationError("%s contains duplicates" % field)
