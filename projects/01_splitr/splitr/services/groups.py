from .. import db, validation
from ..errors import GroupNotFound, ValidationError
from ..repositories import groups as groups_repo
from . import users as users_service


def require_group(group_id):
    """Raise ``GroupNotFound`` unless ``group_id`` exists."""
    if not groups_repo.exists(group_id):
        raise GroupNotFound("group %s not found" % group_id)


def get_members(group_id):
    """Return the group's members as ``User`` objects, in the order they were added."""
    return groups_repo.members(group_id)


def create_group(name, member_ids):
    """Insert a group and link its members atomically.

    Runs in a single transaction: if any membership insert fails, the group row
    is rolled back too, so no partial group is left behind.

    Args:
        name: Group name.
        member_ids: List of existing user ids to add as members.

    Returns:
        The new ``Group``.

    Raises:
        ValidationError: If the name is invalid or the members are not a
            non-empty list of unique, existing user ids.
    """
    if not validation.is_name(name):
        raise ValidationError("name must be a non-empty string")
    validation.validate_ids(member_ids, "members")
    users_service.require_users(member_ids)
    with db.transaction():
        group = groups_repo.insert(name)
        for user_id in member_ids:
            groups_repo.add_member(group.id, user_id)
    return group
