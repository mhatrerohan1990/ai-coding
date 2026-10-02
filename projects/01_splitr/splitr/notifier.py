import logging
import time

log = logging.getLogger(__name__)


def send_email(to, subject, body):
    """Send one email (stand-in for a real SMTP client).

    Simulates the provider: rejects empty/malformed addresses and takes ~100ms
    per message.

    Raises:
        ValueError: If ``to`` is empty or has no ``@``.
    """
    # Stand-in for the real SMTP client. The provider rejects malformed
    # addresses and takes ~100ms per message.
    if not to or "@" not in to:
        raise ValueError("invalid recipient: %r" % to)
    time.sleep(0.1)
    log.info("email sent to=%s subject=%s", to, subject)


def notify_expense(members, paid_by, amount, description, shares):
    """Email every member who has a share in a new expense.

    Members not in ``shares`` are skipped. Emails are sent one at a time, in
    order, via ``send_email``.

    Args:
        members: List of ``{"name", "email"}`` dicts for the whole group.
        paid_by: Name of the payer (shown in the body).
        amount: Total expense amount.
        description: Expense label; "untitled" is used when empty.
        shares: ``{name: share}`` mapping from ``split_evenly``.
    """
    for m in members:
        if m["name"] not in shares:
            continue
        send_email(
            m["email"],
            "New expense: %s" % (description or "untitled"),
            "%s paid %.2f. Your share is %.2f." % (paid_by, amount, shares[m["name"]]),
        )
