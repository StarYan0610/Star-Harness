import shlex
import sys

from app.db.session import create_session_factory
from app.domain.enums import RunStatus, TaskStatus
from app.executors.base import CodingExecutor
from app.repositories.task_repository import TaskRepository
from app.reviewers.command import CommandReviewer
from app.schemas.plan import Plan
from app.schemas.task import CodingTask, ExecutionResult, ReviewContext
from app.services.run_service import RunService


def _python_command(source: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}"


def _task(*, commands: list[str]) -> CodingTask:
    return CodingTask(
        task_id="task-one",
        order_index=1,
        title="Verify task",
        description="Run verification commands.",
        verification_commands=commands,
    )


def _context(project, task_dir) -> ReviewContext:
    return ReviewContext(run_id="run-one", path=str(project), task_dir=str(task_dir))


def _successful_execution() -> ExecutionResult:
    return ExecutionResult(success=True, summary="executor completed", exit_code=0)


def test_command_reviewer_runs_commands_in_order_in_project_directory(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    task_dir = tmp_path / "task-artifacts"
    commands = [
        _python_command("from pathlib import Path; Path('order.txt').write_text('first'); print('first command')"),
        _python_command(
            "from pathlib import Path; assert Path('order.txt').read_text() == 'first'; print('second command')"
        ),
    ]

    review = CommandReviewer(timeout_seconds=5).review(
        _task(commands=commands),
        _successful_execution(),
        _context(project, task_dir),
    )

    assert review.status == "PASSED"
    assert project.joinpath("order.txt").read_text(encoding="utf-8") == "first"
    assert [finding["status"] for finding in review.findings] == ["PASSED", "PASSED"]
    log_text = task_dir.joinpath("verification.log").read_text(encoding="utf-8")
    assert "first command" in log_text
    assert "second command" in log_text


def test_command_reviewer_stops_after_failed_command(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    task_dir = tmp_path / "task-artifacts"
    commands = [
        _python_command("import sys; print('failed command'); sys.exit(7)"),
        _python_command("from pathlib import Path; Path('must-not-exist').write_text('unexpected')"),
    ]

    review = CommandReviewer(timeout_seconds=5).review(
        _task(commands=commands),
        _successful_execution(),
        _context(project, task_dir),
    )

    assert review.status == "FAILED"
    assert "exited with code 7" in review.summary
    assert not project.joinpath("must-not-exist").exists()
    assert len(review.findings) == 1


def test_command_reviewer_does_not_run_commands_when_basic_check_fails(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    task_dir = tmp_path / "task-artifacts"
    command = _python_command("from pathlib import Path; Path('must-not-exist').write_text('unexpected')")

    review = CommandReviewer(timeout_seconds=5).review(
        _task(commands=[command]),
        ExecutionResult(success=False, summary="executor failed", exit_code=1),
        _context(project, task_dir),
    )

    assert review.status == "FAILED"
    assert not project.joinpath("must-not-exist").exists()


def test_command_reviewer_treats_timeout_as_failure(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    task_dir = tmp_path / "task-artifacts"

    review = CommandReviewer(timeout_seconds=0.05).review(
        _task(commands=[_python_command("import time; time.sleep(1)")]),
        _successful_execution(),
        _context(project, task_dir),
    )

    assert review.status == "FAILED"
    assert "timed out" in review.summary
    assert review.findings[0]["timed_out"] is True


def test_command_reviewer_uses_basic_check_when_no_commands(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    reviewer = CommandReviewer()
    task = _task(commands=[])
    context = _context(project, tmp_path / "task-artifacts")

    passed = reviewer.review(task, _successful_execution(), context)
    failed = reviewer.review(
        task,
        ExecutionResult(success=True, summary="   ", exit_code=0),
        context,
    )

    assert passed.status == "PASSED"
    assert "未配置命令验收，仅基础检查" in passed.summary
    assert failed.status == "FAILED"
    assert "未配置命令验收，仅基础检查" in failed.summary


class FakeExecutor(CodingExecutor):
    def __init__(self):
        self.calls: list[str] = []

    def execute(self, task, context, on_output=None) -> ExecutionResult:
        self.calls.append(task.task_id)
        return ExecutionResult(success=True, summary="fake executor completed", exit_code=0)


def test_run_service_marks_failed_command_task_and_skips_following_tasks(tmp_path):
    target = tmp_path / "project"
    fake_executor = FakeExecutor()
    service = RunService(executor=fake_executor, reviewer=CommandReviewer())

    def fake_plan(**kwargs) -> Plan:
        return Plan(
            run_id=kwargs["run_id"],
            strategy_name="test",
            max_tasks=2,
            source_type="requirement",
            source_summary="test command review",
            tasks=[
                CodingTask(
                    task_id="task-one",
                    order_index=1,
                    title="Fail verification",
                    description="The verification command fails.",
                    verification_commands=[_python_command("import sys; sys.exit(3)")],
                ),
                CodingTask(
                    task_id="task-two",
                    order_index=2,
                    title="Must be skipped",
                    description="This task must not execute.",
                ),
            ],
        )

    service.planning_service.create_plan = fake_plan
    service.planning_service.strategy_loader.load = lambda strategy_name: "test strategy"
    run = service.create(
        path=str(target),
        requirement="test command review",
        strategy="test",
        max_tasks=2,
        output="jsonl",
        executor="fake",
    )

    with create_session_factory(target)() as session:
        tasks = TaskRepository(session).list_by_run(run.id)

    assert run.status == RunStatus.FAILED.value
    assert [task.status for task in tasks] == [TaskStatus.FAILED.value, TaskStatus.SKIPPED.value]
    assert fake_executor.calls == ["task-one", "task-one"]
    assert target.joinpath(
        ".coding-agent", "runs", run.id, "tasks", "task-one", "attempt-1", "verification.log"
    ).exists()
    report_text = target.joinpath(".coding-agent", "runs", run.id, "report.md").read_text(encoding="utf-8")
    assert "命令验收失败" in report_text


def test_run_service_reports_basic_check_when_verification_commands_are_absent(tmp_path):
    target = tmp_path / "project"
    service = RunService(executor=FakeExecutor(), reviewer=CommandReviewer())

    def fake_plan(**kwargs) -> Plan:
        return Plan(
            run_id=kwargs["run_id"],
            strategy_name="test",
            max_tasks=1,
            source_type="requirement",
            source_summary="test basic review",
            tasks=[
                CodingTask(
                    task_id="task-one",
                    order_index=1,
                    title="Basic review only",
                    description="No verification command is configured.",
                )
            ],
        )

    service.planning_service.create_plan = fake_plan
    service.planning_service.strategy_loader.load = lambda strategy_name: "test strategy"
    run = service.create(
        path=str(target),
        requirement="test basic review",
        strategy="test",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    report_text = target.joinpath(".coding-agent", "runs", run.id, "report.md").read_text(encoding="utf-8")
    assert run.status == RunStatus.SUCCESS.value
    assert "未配置命令验收，仅基础检查" in report_text
