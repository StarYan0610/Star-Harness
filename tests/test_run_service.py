import json

from app.executors.codex import CodexExecutor
from app.planners.simple import SimplePlanner
from app.reviewers.basic import BasicReviewer
from app.schemas.task import ExecutionResult
from app.services.planning_service import PlanningService
from app.services.run_service import RunService


def test_run_service_plan_and_tasks_are_consistent(tmp_path, monkeypatch):
    target = tmp_path / "project"

    def fake_execute(self, task, context, on_output=None):
        if on_output:
            on_output("fake progress")
        return ExecutionResult(success=True, summary=f"done {task.title}", exit_code=0, log_path=f"{context.task_dir}/executor.log")

    monkeypatch.setattr(CodexExecutor, "execute", fake_execute)

    service = RunService(reviewer=BasicReviewer())
    service.planning_service = PlanningService(planner=SimplePlanner())

    run = service.create(
        path=str(target),
        requirement="搭建项目",
        strategy="skeleton-first",
        max_tasks=2,
        output="jsonl",
        executor="codex",
    )

    plan_path = target / run.plan_path
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_task_ids = [item["task_id"] for item in plan["tasks"]]
    assert run.total_tasks == 2
    assert run.completed_task_ids == plan_task_ids
    assert run.failed_task_ids == []
    assert (target / ".coding-agent" / "runs" / run.id / "report.md").exists()
