from __future__ import annotations

from uuid import uuid4


def generate_uuid() -> str:
    """Generate a UUID4 identifier using the canonical string representation."""
    return str(uuid4())
