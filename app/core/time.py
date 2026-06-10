from __future__ import annotations

from datetime import datetime, timezone


def naive_utcnow() -> datetime:
    """Naive UTC timestamp; DB columns and schemas store naive UTC by contract."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
