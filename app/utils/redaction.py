from __future__ import annotations

import re
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?(?:token|key)|refresh[_-]?token|id[_-]?token|"
    r"private[_-]?key|secret|password|passwd|authorization|credential|(?:^|[_-])token(?:$|[_-]))",
    re.IGNORECASE,
)
_SENSITIVE_LABEL = (
    r"(?:[A-Za-z][A-Za-z0-9_-]*[_-])?"
    r"(?:api[_-]?key|access[_-]?(?:token|key)|refresh[_-]?token|id[_-]?token|"
    r"private[_-]?key|secret|password|passwd|authorization|credential|token)"
)
_ASSIGNMENT = re.compile(
    rf"(?ix)(?P<prefix>\b(?:\"?{_SENSITIVE_LABEL}\"?)\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_KNOWN_TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{12,})\b")


def redact_text(value: object | None) -> str:
    """Redact common credential forms before text crosses an output boundary."""
    text = "" if value is None else str(value)
    text = _BEARER.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    text = _ASSIGNMENT.sub(lambda match: f"{match.group('prefix')}{REDACTED}", text)
    return _KNOWN_TOKEN.sub(REDACTED, text)


def redact_data(value: Any) -> Any:
    """Recursively redact structured event, plan, and finding payloads."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            key: REDACTED if _SENSITIVE_KEY.search(str(key)) else redact_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_data(item) for item in value)
    return value
