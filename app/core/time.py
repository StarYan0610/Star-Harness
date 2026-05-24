from __future__ import annotations

from datetime import datetime, timezone


def naive_utcnow() -> datetime:
    """Return UTC with timezone metadata removed for naive database columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
