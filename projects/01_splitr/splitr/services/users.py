import uuid

from .. import db, validation
from ..errors import UserNotFound, ValidationError
from ..models import User
from ..repositories import users as users_repo


def create_user(name, email=None):
    """Create a user with a fresh random UUID.

    Args:
        name: Display name (non-empty string).
        email: Optional address used for notifications; may change later.

    Returns:
        The new ``User``.

    Raises:
        ValidationError: If the name or email is invalid.
    """
    validation.validate_user_fields({"name": name, "email": email})
    user = User(id=str(uuid.uuid4()), name=name, email=email)
    with db.transaction():
        users_repo.insert(user)
    return user


def get_user(user_id):
    """Return the ``User`` with this id.

    Raises:
        UserNotFound: If no such user exists.
    """
    user = users_repo.get(user_id)
    if user is None:
        raise UserNotFound("user %s not found" % user_id)
    return user


def update_user(user_id, **fields):
    """Change a user's ``name`` and/or ``email``; other keys are ignored.

    Because everything else references the user's id, a rename or email change
    applies everywhere at once and history is untouched. ``email=None`` clears
    the address.

    Returns:
        The updated ``User``.

    Raises:
        UserNotFound: If no such user exists.
        ValidationError: If nothing to update was given or a value is invalid.
    """
    updates = {k: fields[k] for k in users_repo.UPDATABLE_COLUMNS if k in fields}
    if not updates:
        raise ValidationError("provide name and/or email to update")
    get_user(user_id)
    validation.validate_user_fields(updates)
    with db.transaction():
        users_repo.update(user_id, updates)
    return get_user(user_id)


def require_users(user_ids):
    """Raise ``ValidationError`` if any of ``user_ids`` is not an existing user."""
    unknown = set(user_ids) - users_repo.existing_ids(user_ids)
    if unknown:
        raise ValidationError("unknown user ids: %s" % sorted(unknown))
