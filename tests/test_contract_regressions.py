from app.core.config import settings
from app.db.session import create_session_factory
from app.domain.enums import ReviewStatus, TaskStatus
from app.domain.state_machine import WorkflowStateMachine
from app.executors.base import CodingExecutor
from app.models.task import Task
from app.repositories.task_repository import TaskRepository
from app.reviewers.base import Reviewer
from app.reviewers.basic import BasicReviewer
from app.reviewers.command import CommandReviewer
from app.schemas.plan import Plan
from app.schemas.task import CodingTask, ExecutionResult, ReviewResult
from app.services.run_service import RunService


class FailedExecutor(CodingExecutor):
    def execute(self, task, context, on_output=None) -> ExecutionResult:
        return ExecutionResult(success=False, summary="executor failed", exit_code=1)


class VerboseExecutor(CodingExecutor):
    def execute(self, task, context, on_output=None) -> ExecutionResult:
        return ExecutionResult(success=True, summary="x" * 300, exit_code=0)


class PermissiveReviewer(Reviewer):
    def review(self, task, result, context) -> ReviewResult:
        return ReviewResult(status=ReviewStatus.PASSED.value, summary="reviewer claimed success")


class VerboseReviewer(Reviewer):
    def review(self, task, result, context) -> ReviewResult:
        return ReviewResult(status=ReviewStatus.PASSED.value, summary="y" * 300)


def _install_single_task_plan(service: RunService) -> None:
    def fake_plan(**kwargs) -> Plan:
        return Plan(
            run_id=kwargs["run_id"],
            strategy_name="test",
            max_tasks=1,
            source_type="requirement",
            source_summary="test",
            tasks=[CodingTask(task_id="task", order_index=1, title="Task", description="Do work.")],
        )

    service.planning_service.create_plan = fake_plan
    service.planning_service.strategy_loader.load = lambda strategy_name: "test strategy"


def test_default_reviewer_routes_through_configuration(monkeypatch):
    monkeypatch.setattr(settings, "default_reviewer", "command")
    assert isinstance(RunService(executor=FailedExecutor()).reviewer, CommandReviewer)

    monkeypatch.setattr(settings, "default_reviewer", "basic")
    assert isinstance(RunService(executor=FailedExecutor()).reviewer, BasicReviewer)


def test_execution_failure_cannot_pass_when_reviewer_claims_success(tmp_path):
    target = tmp_path / "project"
    service = RunService(executor=FailedExecutor(), reviewer=PermissiveReviewer(), max_task_attempts=1)
    _install_single_task_plan(service)

    run = service.create(
        path=str(target),
        requirement="test review gate",
        strategy="test",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    with create_session_factory(target)() as session:
        task = TaskRepository(session).list_by_run(run.id)[0]

    assert run.status == "FAILED"
    assert task.status == "FAILED"
    assert task.review_status == "FAILED"
    assert {finding["kind"] for finding in task.review_findings} == {"execution_failure"}
    assert all(finding.get("kind") != "attempt" for finding in task.review_findings)


def test_report_summaries_are_truncated_with_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "retry_feedback_max_chars", 60)
    target = tmp_path / "project"
    service = RunService(executor=VerboseExecutor(), reviewer=VerboseReviewer())
    _install_single_task_plan(service)

    run = service.create(
        path=str(target),
        requirement="r" * 300,
        strategy="test",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    report = target.joinpath(".coding-agent", "runs", run.id, "report.md").read_text(encoding="utf-8")
    assert run.status == "SUCCESS"
    assert "...[truncated]" in report
    assert "x" * 100 not in report
    assert "y" * 100 not in report


def test_review_metadata_update_keeps_reviewing_state_explicit():
    task = Task(
        id="task",
        run_id="run",
        title="Task",
        description="Description",
        order_index=1,
        executor_type="fake",
    )
    state_machine = WorkflowStateMachine()
    state_machine.transition_task(task, TaskStatus.RUNNING)
    state_machine.transition_task(task, TaskStatus.REVIEWING)

    state_machine.update_task_review(
        task,
        review_status="FAILED",
        review_summary="verification failed",
        review_findings=[{"kind": "verification_command"}],
    )

    assert task.status == TaskStatus.REVIEWING.value
    assert task.review_findings == [{"kind": "verification_command"}]
