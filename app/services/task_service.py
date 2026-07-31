from __future__ import annotations

from app.models.task import Task
from app.schemas.plan import Plan


class TaskService:
    def tasks_from_plan(self, plan: Plan, *, executor_type: str) -> list[Task]:
        return [
            Task(
                id=item.task_id,
                run_id=plan.run_id,
                title=item.title,
                description=item.description,
                order_index=item.order_index,
                executor_type=executor_type,
                scope=item.scope,
                acceptance_criteria=item.acceptance_criteria,
                verification_commands=item.verification_commands,
            )
            for item in plan.tasks
        ]
