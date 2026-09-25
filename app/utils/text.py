from __future__ import annotations


def truncate_text(value: object | None, max_chars: int, *, keep_tail: bool = False) -> str:
    """Bound summary length, preserving a truncation marker and optionally the tail."""
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text

    marker = "\n...[truncated]"
    if max_chars <= len(marker):
        return marker[:max_chars]
    visible_chars = max_chars - len(marker)
    if keep_tail:
        return text[-visible_chars:] + marker
    return text[:visible_chars] + marker
