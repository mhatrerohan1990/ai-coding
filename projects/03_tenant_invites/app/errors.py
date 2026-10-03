class InvalidInviteError(Exception):
    """Token is malformed, unknown, wrong, or expired (deliberately one error)."""


class AlreadyMemberError(Exception):
    """The invited email already belongs to a member of the tenant."""


class InviteUsedError(Exception):
    """The token is genuine but the invite was already redeemed (including by a concurrent request)."""
