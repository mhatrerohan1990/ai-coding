import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

log = logging.getLogger(__name__)

MAX_WORKERS = 4
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="notifier")
_pending = set()
_pending_lock = threading.Lock()


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
    order. A failure for one recipient (e.g. a missing or invalid address) is
    logged and does not stop the remaining recipients from being notified.

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
        try:
            send_email(
                m["email"],
                "New expense: %s" % (description or "untitled"),
                "%s paid %.2f. Your share is %.2f." % (paid_by, amount, shares[m["name"]]),
            )
        except Exception:
            log.exception("could not notify %s about expense", m["name"])


def notify_expense_async(members, paid_by, amount, description, shares):
    """Queue ``notify_expense`` on a background worker and return immediately.

    The request thread no longer waits ~100ms per recipient. Work runs on a
    small thread pool (``MAX_WORKERS``); queued emails are held in memory only,
    so they are lost if the process is killed (a durable queue/outbox would be
    the production answer). Arguments are snapshotted so later changes by the
    caller cannot affect what is sent.

    Returns:
        The ``concurrent.futures.Future`` for the queued job.
    """
    future = _executor.submit(
        notify_expense,
        [dict(m) for m in members],
        paid_by,
        amount,
        description,
        dict(shares),
    )
    with _pending_lock:
        _pending.add(future)
    future.add_done_callback(_forget)
    return future


def _forget(future):
    with _pending_lock:
        _pending.discard(future)


def wait_for_pending(timeout=None):
    """Block until all queued notifications have finished (used by tests).

    Returns:
        True if everything finished within ``timeout`` seconds, else False.
    """
    with _pending_lock:
        futures = list(_pending)
    _, not_done = wait(futures, timeout=timeout)
    return not not_done
