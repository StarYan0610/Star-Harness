from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.run import AuditItem
from app.schemas.task import CodingTask


class Plan(BaseModel):
    run_id: str
    strategy_name: str
    max_tasks: int
    source_type: str
    source_summary: str
    truncated: bool = False
    truncation_reason: str | None = None
    audit_total_items: int = 0
    unprocessed_audit_items: list[AuditItem] = Field(default_factory=list)
    tasks: list[CodingTask] = Field(default_factory=list)
