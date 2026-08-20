from __future__ import annotations

from uuid import uuid4


def generate_uuid() -> str:
    return str(uuid4())
