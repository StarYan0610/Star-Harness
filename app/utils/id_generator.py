from __future__ import annotations

from uuid import uuid4


def generate_uuid() -> str:
    """Return a UUID4 identifier in the standard hyphenated string format."""
    identifier = uuid4()
    return str(identifier)
