import logging
import time

log = logging.getLogger(__name__)


def send_email(to, subject, body):
    # Stand-in for the real SMTP client. The provider rejects malformed
    # addresses and takes ~100ms per message.
    if not to or "@" not in to:
        raise ValueError("invalid recipient: %r" % to)
    time.sleep(0.1)
    log.info("email sent to=%s subject=%s", to, subject)


def notify_expense(members, paid_by, amount, description, shares):
    for m in members:
        if m["name"] not in shares:
            continue
        send_email(
            m["email"],
            "New expense: %s" % (description or "untitled"),
            "%s paid %.2f. Your share is %.2f." % (paid_by, amount, shares[m["name"]]),
        )
