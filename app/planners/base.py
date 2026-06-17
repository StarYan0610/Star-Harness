from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.plan import Plan
from app.schemas.run import AuditReport


class Planner(ABC):
    @abstractmethod
    def plan(
        self,
        *,
        run_id: str,
        command: str,
        path: str,
        requirement: str | None,
        update_mode: str | None,
        audit_report: AuditReport | None,
        strategy_name: str,
        strategy_text: str,
        max_tasks: int,
        project_memory: str = "",
    ) -> Plan:
        raise NotImplementedError
