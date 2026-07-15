from __future__ import annotations

import json
import re
from pathlib import Path

from app.schemas.run import AuditItem, AuditReport


_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_SEVERITY_PREFIX = re.compile(r"^\s*(?:\[\s*)?(critical|high|medium|low|warning|info|blocker|p[0-3])(?:\s*\])?\s*[:|-]\s*", re.IGNORECASE)
_BRACKETED_SEVERITY_PREFIX = re.compile(
    r"^\s*\[\s*(critical|high|medium|low|warning|info|blocker|p[0-3])\s*\]\s*",
    re.IGNORECASE,
)


def load_audit_report(path: str) -> AuditReport:
    """Load an audit report and normalize supported JSON or plain-text findings."""
    report_path = Path(path).expanduser()
    raw = report_path.read_text(encoding="utf-8")
    entries = _json_entries(json.loads(raw)) if report_path.suffix.lower() == ".json" else _text_entries(raw)
    items = [_to_audit_item(entry) for entry in entries]
    items = [item for item in items if item is not None]
    items = [item for _, item in sorted(enumerate(items), key=lambda pair: (_SEVERITY_ORDER[pair[1].severity], pair[0]))]
    findings = [_item_summary(item) for item in items]
    summary = findings[0] if findings else report_path.name
    return AuditReport(
        path=str(report_path),
        raw_content=raw,
        summary=summary,
        items=items,
        findings=findings,
        priority_items=findings,
    )


def _json_entries(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return [payload]
    for key in ("findings", "issues", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [payload] if any(key in payload for key in ("title", "name", "summary", "description", "detail")) else []


def _text_entries(raw: str) -> list[object]:
    """Split a plain-text audit report into candidate finding entries."""
    entries: list[object] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal heading, body
        if heading and body:
            entries.append({"title": heading, "description": " ".join(body)})
        elif heading and _severity_prefix_match(heading):
            entries.append(heading)
        elif body:
            entries.append(" ".join(body))
        heading = None
        body = []

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        heading_match = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading_match:
            flush()
            heading = heading_match.group(1).strip()
            continue
        bullet_match = re.match(r"^[-*+]\s+(.+)$", line)
        if bullet_match:
            if body:
                flush()
            entries.append(bullet_match.group(1).strip())
            continue
        body.append(line)
    flush()
    return entries


def _to_audit_item(entry: object) -> AuditItem | None:
    if isinstance(entry, dict):
        raw_severity = _first_text(entry, "severity", "level", "priority", "risk")
        title = _first_text(entry, "title", "name", "summary", "issue", "id")
        description = _first_text(entry, "description", "detail", "message", "details", "recommendation")
        if not raw_severity and title:
            severity_match = _severity_prefix_match(title)
            if severity_match:
                raw_severity = severity_match.group(1)
                title = title[severity_match.end() :].strip()
        if not title and description:
            title = description[:120]
        if not title:
            return None
        return AuditItem(
            severity=_normalize_severity(raw_severity),
            title=title,
            description=description or title,
            raw_severity=raw_severity or None,
        )
    if entry is None:
        return None
    return _item_from_text(str(entry))


def _item_from_text(value: str) -> AuditItem | None:
    text = value.strip().strip("-*# \t")
    if not text:
        return None
    severity_match = _severity_prefix_match(text)
    raw_severity = severity_match.group(1) if severity_match else ""
    body = text[severity_match.end() :].strip() if severity_match else text
    if not body:
        return None
    title, separator, description = body.partition(": ")
    if not separator:
        title, separator, description = body.partition(" - ")
    title = title.strip() or body[:120]
    description = description.strip() if separator else body
    return AuditItem(
        severity=_normalize_severity(raw_severity),
        title=title,
        description=description or title,
        raw_severity=raw_severity or None,
    )


def _normalize_severity(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"critical", "high", "blocker", "p0", "p1"}:
        return "high"
    if lowered in {"low", "info", "p3"}:
        return "low"
    return "medium"


def _severity_prefix_match(value: str) -> re.Match[str] | None:
    return _SEVERITY_PREFIX.match(value) or _BRACKETED_SEVERITY_PREFIX.match(value)


def _first_text(entry: dict, *keys: str) -> str:
    for key in keys:
        value = entry.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _item_summary(item: AuditItem) -> str:
    return f"[{item.severity}] {item.title}: {item.description}"
