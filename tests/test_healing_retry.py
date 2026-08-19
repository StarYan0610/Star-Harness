import json
import shlex
import sys
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.db.session import create_session_factory
from app.domain.enums import RunStatus, TaskStatus
from app.executors.base import CodingExecutor
from app.repositories.task_repository import TaskRepository
from app.reviewers.command import CommandReviewer
from app.schemas.plan import Plan
from app.schemas.task import CodingTask, ExecutionResult
from app.services.run_service import RunService


def _python_command(source: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}"


def _install_plan(service: RunService, tasks: list[CodingTask]) -> None:
    def fake_plan(**kwargs) -> Plan:
        return Plan(
            run_id=kwargs["run_id"],
            strategy_name="test",
            max_tasks=len(tasks),
            source_type="requirement",
            source_summary="healing retry test",
            tasks=tasks,
        )

    service.planning_service.create_plan = fake_plan
    service.planning_service.strategy_loader.load = lambda strategy_name: "test strategy"


def _run(service: RunService, target: Path, *, max_tasks: int) -> object:
    return service.create(
        path=str(target),
        requirement="exercise healing retry",
        strategy="test",
        max_tasks=max_tasks,
        output="jsonl",
        executor="fake",
    )


def _task(task_id: str, order_index: int, *, commands: list[str] | None = None) -> CodingTask:
    return CodingTask(
        task_id=task_id,
        order_index=order_index,
        title=f"Task {order_index}",
        description="Test retry orchestration.",
        verification_commands=commands or [],
    )


def _load_tasks(target: Path, run_id: str):
    with create_session_factory(target)() as session:
        return TaskRepository(session).list_by_run(run_id)


class ScriptedExecutor(CodingExecutor):
    def __init__(self, outcomes: list[bool]):
        self.outcomes = outcomes
        self.contexts = []
        self.task_ids: list[str] = []

    def execute(self, task, context, on_output=None) -> ExecutionResult:
        self.contexts.append(context)
        self.task_ids.append(task.task_id)
        task_dir = Path(context.task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        log_path = task_dir / "executor.log"
        log_path.write_text(f"attempt={context.attempt}\n", encoding="utf-8")
        success = self.outcomes[len(self.contexts) - 1]
        return ExecutionResult(
            success=success,
            summary="execution passed" if success else "execution failed",
            exit_code=0 if success else 1,
            error_message=None if success else "intentional failure",
            log_path=str(log_path),
        )


class RepairingExecutor(CodingExecutor):
    def __init__(self):
        self.contexts = []

    def execute(self, task, context, on_output=None) -> ExecutionResult:
        self.contexts.append(context)
        task_dir = Path(context.task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        log_path = task_dir / "executor.log"
        log_path.write_text(f"attempt={context.attempt}\n", encoding="utf-8")
        if context.attempt == 2:
            assert context.retry_feedback is not None
            assert context.retry_feedback.review_findings[0]["kind"] == "verification_command"
            assert "exit_code: 1" in context.retry_feedback.verification_log_excerpt
            Path(context.path, "ready").write_text("ready", encoding="utf-8")
        return ExecutionResult(success=True, summary="execution passed", exit_code=0, log_path=str(log_path))


def test_execution_failure_retries_once_by_default_and_records_feedback(tmp_path):
    target = tmp_path / "project"
    executor = ScriptedExecutor([False, True])
    service = RunService(executor=executor, reviewer=CommandReviewer())
    _install_plan(service, [_task("task-one", 1)])

    run = _run(service, target, max_tasks=1)
    tasks = _load_tasks(target, run.id)
    report_text = target.joinpath(".coding-agent", "runs", run.id, "report.md").read_text(encoding="utf-8")
    events = [
        json.loads(line)
        for line in target.joinpath(".coding-agent", "runs", run.id, "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    artifact_history = json.loads(
        target.joinpath(".coding-agent", "runs", run.id, "tasks", "task-one", "attempts.json").read_text(
            encoding="utf-8"
        )
    )["attempts"]

    assert run.status == RunStatus.SUCCESS.value
    assert tasks[0].status == TaskStatus.PASSED.value
    assert [context.attempt for context in executor.contexts] == [1, 2]
    assert executor.contexts[1].retry_feedback is not None
    assert executor.contexts[1].retry_feedback.failed_attempt == 1
    assert "attempt=1" in executor.contexts[1].retry_feedback.executor_log_excerpt
    assert tasks[0].review_findings == [{"kind": "basic_check", "status": "PASSED"}]
    assert [record["outcome"] for record in artifact_history] == ["RETRYING", "PASSED"]
    assert "Attempts: 2 / 2" in report_text
    assert "Attempt 1: RETRYING" in report_text
    assert "TASK_RETRY_SCHEDULED" in [event["event_type"] for event in events]


def test_verification_failure_is_injected_before_retry(tmp_path):
    target = tmp_path / "project"
    executor = RepairingExecutor()
    service = RunService(executor=executor, reviewer=CommandReviewer())
    _install_plan(
        service,
        [
            _task(
                "task-one",
                1,
                commands=[_python_command("from pathlib import Path; assert Path('ready').exists()")],
            )
        ],
    )

    run = _run(service, target, max_tasks=1)
    tasks = _load_tasks(target, run.id)

    assert run.status == RunStatus.SUCCESS.value
    assert tasks[0].status == TaskStatus.PASSED.value
    assert [context.attempt for context in executor.contexts] == [1, 2]
    assert tasks[0].review_findings[0]["kind"] == "verification_command"


def test_final_retry_failure_marks_following_tasks_skipped(tmp_path):
    target = tmp_path / "project"
    executor = ScriptedExecutor([False, False])
    service = RunService(executor=executor, reviewer=CommandReviewer())
    _install_plan(service, [_task("task-one", 1), _task("task-two", 2)])

    run = _run(service, target, max_tasks=2)
    tasks = _load_tasks(target, run.id)
    report_text = target.joinpath(".coding-agent", "runs", run.id, "report.md").read_text(encoding="utf-8")

    assert run.status == RunStatus.FAILED.value
    assert [task.status for task in tasks] == [TaskStatus.FAILED.value, TaskStatus.SKIPPED.value]
    assert executor.task_ids == ["task-one", "task-one"]
    assert tasks[0].review_findings[0]["kind"] == "basic_check"
    assert "Attempts: 2 / 2" in report_text
    assert "Attempt 2: FAILED" in report_text


def test_retry_attempt_limit_is_configurable_and_hard_limited(tmp_path):
    target = tmp_path / "project"
    executor = ScriptedExecutor([False, False, True])
    service = RunService(executor=executor, max_task_attempts=3)
    _install_plan(service, [_task("task-one", 1)])

    run = _run(service, target, max_tasks=1)

    assert run.status == RunStatus.SUCCESS.value
    assert [context.attempt for context in executor.contexts] == [1, 2, 3]
    with pytest.raises(ValidationError, match="max task attempts"):
        RunService(max_task_attempts=5)
