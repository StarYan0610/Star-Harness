from __future__ import annotations

from pydantic import BaseModel


class ReportSummary(BaseModel):
    run_id: str
    status: str
    report_path: str
