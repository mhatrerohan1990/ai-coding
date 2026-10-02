"""The app's single source of time, so every timestamp is UTC and tests can control it."""

from datetime import datetime, timezone


def utc_now():
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(timezone.utc)


def utc_now_iso():
    """Return the current UTC time as ISO 8601 text, e.g. ``2026-10-02T12:00:00.123456+00:00``.

    Always UTC with microseconds and an explicit offset, so the strings stored
    in the database sort chronologically and mean the same thing on any server.
    """
    return utc_now().isoformat(timespec="microseconds")
