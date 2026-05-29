from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.time import naive_utcnow


class ProgressEvent(BaseModel):
    id: str
    run_id: str
    event_type: str
    message: str
    task_id: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=naive_utcnow)
