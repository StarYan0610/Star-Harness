import json
import subprocess
from pathlib import Path

from app.executors.base import CodingExecutor
from app.git.command import CommandGitInspector
from app.planners.simple import SimplePlanner
from app.reviewers.basic import BasicReviewer
from app.schemas.task import ExecutionResult
from app.services.planning_service import PlanningService
from app.services.run_service import RunService


def _git(target: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=target,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _init_repository(target: Path) -> None:
    target.mkdir()
    _git(target, "init")
    _git(target, "config", "user.email", "tests@example.invalid")
    _git(target, "config", "user.name", "Coding Harness Tests")
    target.joinpath("app.txt").write_text("initial\n", encoding="utf-8")
    _git(target, "add", "app.txt")
    _git(target, "commit", "-m", "initial")


class NoopExecutor(CodingExecutor):
    def execute(self, task, context, on_output=None) -> ExecutionResult:
        return ExecutionResult(success=True, summary="completed", exit_code=0)


class WritingExecutor(CodingExecutor):
    def execute(self, task, context, on_output=None) -> ExecutionResult:
        Path(context.path, "changed-by-run.txt").write_text("changed\n", encoding="utf-8")
        return ExecutionResult(success=True, summary="completed", exit_code=0)


def _run_update(service: RunService, target: Path):
    return service.update(
        path=str(target),
        update_mode="requirement",
        requirement="make a focused change",
        audit_report_path=None,
        strategy="skeleton-first",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )


def _with_simple_planner(service: RunService) -> RunService:
    service.planning_service = PlanningService(planner=SimplePlanner())
    return service


def test_git_inspector_ignores_harness_artifacts_and_reports_dirty_files(tmp_path):
    target = tmp_path / "project"
    _init_repository(target)
    target.joinpath("app.txt").write_text("changed\n", encoding="utf-8")
    target.joinpath(".coding-agent").mkdir()
    target.joinpath(".coding-agent", "events.jsonl").write_text("{}\n", encoding="utf-8")

    snapshot = CommandGitInspector().inspect(target)

    assert snapshot.is_repository is True
    assert snapshot.branch
    assert snapshot.dirty is True
    assert snapshot.affected_files == ["app.txt"]
    assert "app.txt" in snapshot.diff_summary


def test_create_accepts_a_git_metadata_only_directory_and_records_precheck(tmp_path):
    target = tmp_path / "project"
    target.mkdir()
    _git(target, "init")
    _git(target, "config", "user.email", "tests@example.invalid")
    _git(target, "config", "user.name", "Coding Harness Tests")
    service = _with_simple_planner(RunService(executor=NoopExecutor(), reviewer=BasicReviewer()))

    run = service.create(
        path=str(target),
        requirement="create project files",
        strategy="skeleton-first",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    before = json.loads(
        target.joinpath(".coding-agent", "runs", run.id, "git_before.json").read_text(encoding="utf-8")
    )
    assert run.status == "SUCCESS"
    assert before["is_repository"] is True


def test_commit_option_does_not_fail_a_non_git_create(tmp_path):
    target = tmp_path / "project"
    service = _with_simple_planner(
        RunService(executor=NoopExecutor(), reviewer=BasicReviewer(), commit_on_success=True)
    )

    run = service.create(
        path=str(target),
        requirement="create project files",
        strategy="skeleton-first",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    commit = json.loads(
        target.joinpath(".coding-agent", "runs", run.id, "git_commit.json").read_text(encoding="utf-8")
    )
    assert run.status == "SUCCESS"
    assert commit["created"] is False
    assert commit["message"] == "local commit skipped: target is not a Git repository"


def test_dirty_update_continues_by_default_and_writes_git_report(tmp_path):
    target = tmp_path / "project"
    _init_repository(target)
    target.joinpath("app.txt").write_text("dirty\n", encoding="utf-8")
    service = _with_simple_planner(RunService(executor=NoopExecutor(), reviewer=BasicReviewer()))

    run = _run_update(service, target)

    run_dir = target / ".coding-agent" / "runs" / run.id
    report = run_dir.joinpath("report.md").read_text(encoding="utf-8")
    before = json.loads(run_dir.joinpath("git_before.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in run_dir.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert run.status == "SUCCESS"
    assert before["dirty"] is True
    assert before["affected_files"] == ["app.txt"]
    assert "## Git Safety" in report
    assert "Before Dirty: True" in report
    assert "app.txt" in report
    assert {event["event_type"] for event in events} >= {"GIT_PRECHECK", "GIT_POSTCHECK", "GIT_DIRTY_WARNING"}


def test_successful_run_can_create_a_local_commit_without_staging_artifacts(tmp_path):
    target = tmp_path / "project"
    _init_repository(target)
    before_head = _git(target, "rev-parse", "HEAD")
    service = _with_simple_planner(
        RunService(executor=WritingExecutor(), reviewer=BasicReviewer(), commit_on_success=True)
    )

    run = _run_update(service, target)

    after_head = _git(target, "rev-parse", "HEAD")
    status = _git(target, "status", "--porcelain")
    commit = json.loads(
        target.joinpath(".coding-agent", "runs", run.id, "git_commit.json").read_text(encoding="utf-8")
    )

    assert run.status == "SUCCESS"
    assert after_head != before_head
    assert commit["created"] is True
    assert "changed-by-run.txt" in _git(target, "show", "--name-only", "--format=", "HEAD")
    assert all(".coding-agent" in line for line in status.splitlines())


def test_commit_on_success_does_not_stage_changes_that_precede_the_run(tmp_path):
    target = tmp_path / "project"
    _init_repository(target)
    target.joinpath("app.txt").write_text("user change\n", encoding="utf-8")
    before_head = _git(target, "rev-parse", "HEAD")
    service = _with_simple_planner(
        RunService(executor=WritingExecutor(), reviewer=BasicReviewer(), commit_on_success=True)
    )

    run = _run_update(service, target)

    commit = json.loads(
        target.joinpath(".coding-agent", "runs", run.id, "git_commit.json").read_text(encoding="utf-8")
    )
    status = _git(target, "status", "--porcelain")

    assert run.status == "SUCCESS"
    assert _git(target, "rev-parse", "HEAD") == before_head
    assert commit == {"created": False, "commit_id": None, "message": "local commit skipped: worktree was dirty before run"}
    assert "M app.txt" in status
    assert "?? changed-by-run.txt" in status


def test_require_clean_worktree_creates_a_failed_run_with_report(tmp_path):
    target = tmp_path / "project"
    _init_repository(target)
    target.joinpath("app.txt").write_text("dirty\n", encoding="utf-8")
    service = RunService(
        executor=NoopExecutor(),
        reviewer=BasicReviewer(),
        require_clean_git_worktree=True,
    )

    run = _run_update(service, target)

    run_dir = target / ".coding-agent" / "runs" / run.id
    report = run_dir.joinpath("report.md").read_text(encoding="utf-8")
    events = [
        json.loads(line)
        for line in run_dir.joinpath("events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert run.status == "FAILED"
    assert "require-clean-git-worktree" in (run.error_message or "")
    assert "require-clean-git-worktree" in report
    assert "PROJECT_VALIDATION_FAILED" in [event["event_type"] for event in events]
