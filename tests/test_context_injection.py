import json

from app.executors.base import CodingExecutor
from app.planners.simple import SimplePlanner
from app.reviewers.basic import BasicReviewer
from app.schemas.plan import Plan
from app.schemas.task import CodingTask, CompletedTaskContext, ExecutionResult
from app.services.planning_service import PlanningService
from app.services.run_service import RunService


class CapturingExecutor(CodingExecutor):
    def __init__(self):
        self.contexts = []

    def execute(self, task, context, on_output=None) -> ExecutionResult:
        self.contexts.append(context)
        return ExecutionResult(success=True, summary=f"completed {task.title}", exit_code=0)


def test_memory_and_completed_task_context_are_injected(tmp_path):
    target = tmp_path / "project"
    memory_dir = target / ".coding-agent"
    memory_dir.mkdir(parents=True)
    memory_dir.joinpath("memory.md").write_text("Keep changes focused and update tests.", encoding="utf-8")
    executor = CapturingExecutor()
    service = RunService(executor=executor, reviewer=BasicReviewer())
    captured_planning_kwargs = {}

    def fake_plan(**kwargs) -> Plan:
        captured_planning_kwargs.update(kwargs)
        return Plan(
            run_id=kwargs["run_id"],
            strategy_name="test",
            max_tasks=2,
            source_type="requirement",
            source_summary="context test",
            tasks=[
                CodingTask(
                    task_id="first",
                    order_index=1,
                    title="First task",
                    description="Implement the foundation.",
                    scope=["src/first.py"],
                ),
                CodingTask(
                    task_id="second",
                    order_index=2,
                    title="Second task",
                    description="Build on the foundation.",
                    scope=["src/second.py"],
                ),
            ],
        )

    service.planning_service.create_plan = fake_plan
    service.planning_service.strategy_loader.load = lambda strategy_name: "test strategy"
    run = service.update(
        path=str(target),
        update_mode="requirement",
        requirement="exercise task context",
        audit_report_path=None,
        strategy="test",
        max_tasks=2,
        output="jsonl",
        executor="fake",
    )

    second_context = executor.contexts[1]
    events = [
        json.loads(line)
        for line in target.joinpath(".coding-agent", "runs", run.id, "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert run.status == "SUCCESS"
    assert captured_planning_kwargs["project_memory"] == "Keep changes focused and update tests."
    assert second_context.project_memory == "Keep changes focused and update tests."
    assert second_context.completed_tasks == [
        CompletedTaskContext(
            task_id="first",
            title="First task",
            summary="completed First task",
            key_files=["src/first.py"],
        )
    ]
    assert "MEMORY_LOADED" in [event["event_type"] for event in events]


def test_codex_prompt_contains_structured_run_context():
    from app.executors.codex import CodexExecutor

    task = CodingTask(task_id="second", order_index=2, title="Second", description="Continue work.")
    prompt = CodexExecutor(command="codex").build_prompt(
        task,
        completed_tasks=[
            CompletedTaskContext(
                task_id="first",
                title="First",
                summary="foundation completed",
                key_files=["src/first.py"],
            )
        ],
        project_memory="Use project conventions.",
    )

    assert "项目只读约定" in prompt
    assert "Use project conventions." in prompt
    assert "本 Run 已完成任务" in prompt
    assert "foundation completed" in prompt
    assert "src/first.py" in prompt
