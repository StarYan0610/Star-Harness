from __future__ import annotations

from pydantic import BaseModel, Field


class AuditItem(BaseModel):
    severity: str = "medium"
    title: str
    description: str
    raw_severity: str | None = None


class AuditReport(BaseModel):
    path: str
    raw_content: str
    summary: str
    items: list[AuditItem] = Field(default_factory=list)
    # Compatibility summaries for callers that only need plain-text labels.
    findings: list[str] = Field(default_factory=list)
    priority_items: list[str] = Field(default_factory=list)
