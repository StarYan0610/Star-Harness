from __future__ import annotations

import json
from pathlib import Path

from app.planners.base import Planner
from app.planners.factory import PlannerFactory
from app.planners.strategy_loader import StrategyLoader
from app.schemas.plan import Plan
from app.schemas.run import AuditReport
from app.utils.redaction import redact_data


class PlanningService:
    def __init__(self, strategy_loader: StrategyLoader | None = None, planner: Planner | None = None):
        self.strategy_loader = strategy_loader or StrategyLoader()
        self.planner = planner or PlannerFactory.create()

    def create_plan(
        self,
        *,
        run_id: str,
        command: str,
        path: str,
        requirement: str | None,
        update_mode: str | None,
        audit_report: AuditReport | None,
        strategy_name: str,
        max_tasks: int,
        project_memory: str = "",
    ) -> Plan:
        strategy_text = self.strategy_loader.load(strategy_name)
        return self.planner.plan(
            run_id=run_id,
            command=command,
            path=path,
            requirement=requirement,
            update_mode=update_mode,
            audit_report=audit_report,
            strategy_name=strategy_name,
            strategy_text=strategy_text,
            max_tasks=max_tasks,
            project_memory=project_memory,
        )

    def write_plan_tmp(self, plan: Plan, run_dir: Path) -> Path:
        tmp_path = run_dir / "plan.json.tmp"
        tmp_path.write_text(json.dumps(redact_data(plan.model_dump()), ensure_ascii=False, indent=2), encoding="utf-8")
        return tmp_path
