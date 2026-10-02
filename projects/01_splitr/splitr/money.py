"""Money is stored and calculated as whole cents (integers) and only turned into a
decimal number at the API edge, so no arithmetic ever touches floating point."""

import math

from .errors import ValidationError

MAX_AMOUNT = 1_000_000_000  # the largest amount a request may carry


def parse_amount(amount):
    """Validate a decimal amount from a request and return it as integer cents.

    Args:
        amount: A JSON number such as ``33.34`` (booleans and strings are rejected).

    Returns:
        The amount in cents, e.g. ``3334``.

    Raises:
        ValidationError: If it is not a finite number greater than 0, is larger
            than ``MAX_AMOUNT``, or has more than 2 decimal places.
    """
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValidationError("amount must be a number")
    if not math.isfinite(amount) or amount <= 0:
        raise ValidationError("amount must be greater than 0")
    if amount > MAX_AMOUNT:
        raise ValidationError("amount must not exceed %d" % MAX_AMOUNT)
    cents = round(amount * 100)
    if abs(amount * 100 - cents) > 1e-6:
        raise ValidationError("amount must have at most 2 decimal places")
    return cents


def to_amount(cents):
    """Convert integer cents to the decimal number shown in API responses."""
    return cents / 100
