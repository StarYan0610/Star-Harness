from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BootstrapError, ProjectValidationError, UsageError, ValidationError
from app.core.limits import HARD_MAX_TASK_ATTEMPTS, HARD_MAX_TASKS
from app.core.paths import ensure_absolute_path, run_dir
from app.db.session import create_session_factory
from app.domain.enums import ReviewStatus, RunCommand, RunStatus, TaskStatus, UpdateMode
from app.domain.state_machine import WorkflowStateMachine
from app.executors.base import CodingExecutor
from app.executors.factory import ExecutorFactory
from app.git.base import GitInspector
from app.git.command import CommandGitInspector
from app.models.run import Run
from app.models.task import Task
from app.repositories.run_repository import RunRepository
from app.repositories.task_repository import TaskRepository
from app.reviewers.base import Reviewer
from app.reviewers.factory import ReviewerFactory
from app.schemas.run import AuditReport
from app.schemas.git import GitCommitResult, GitSnapshot
from app.schemas.task import (
    CodingTask,
    CompletedTaskContext,
    ExecutionContext,
    ExecutionResult,
    ReviewContext,
    ReviewResult,
    RetryFeedback,
)
from app.services.planning_service import PlanningService
from app.services.progress_service import ProgressService
from app.services.report_service import ReportService
from app.services.task_service import TaskService
from app.utils.audit import load_audit_report
from app.utils.id_generator import generate_uuid
from app.utils.redaction import redact_data, redact_text
from app.utils.text import truncate_text


class RunService:
    def __init__(
        self,
        *,
        executor: CodingExecutor | None = None,
        reviewer: Reviewer | None = None,
        git_inspector: GitInspector | None = None,
        max_task_attempts: int | None = None,
        require_clean_git_worktree: bool | None = None,
        commit_on_success: bool | None = None,
    ):
        self.state_machine = WorkflowStateMachine()
        self.planning_service = PlanningService()
        self.task_service = TaskService()
        self.report_service = ReportService()
        self.executor = executor
        self.reviewer = reviewer or ReviewerFactory.create(settings.default_reviewer)
        self.git_inspector = git_inspector or CommandGitInspector()
        self.require_clean_git_worktree = (
            settings.require_clean_git_worktree
            if require_clean_git_worktree is None
            else require_clean_git_worktree
        )
        self.commit_on_success = settings.commit_on_success if commit_on_success is None else commit_on_success
        self.max_task_attempts = settings.max_task_attempts if max_task_attempts is None else max_task_attempts
        if not 1 <= self.max_task_attempts <= HARD_MAX_TASK_ATTEMPTS:
            raise UsageError(f"max task attempts must be between 1 and {HARD_MAX_TASK_ATTEMPTS}")
        if settings.retry_feedback_max_chars < 5:
            raise ValidationError("retry feedback max chars must be at least 5")
        self.retry_feedback_max_chars = settings.retry_feedback_max_chars

    def create(
        self,
        *,
        path: str,
        requirement: str,
        strategy: str,
        max_tasks: int,
        output: str,
        executor: str,
    ) -> Run:
        self._validate_max_tasks(max_tasks)
        target, create_target_was_nonempty = self._bootstrap_create_target(path)
        return self._run(
            command=RunCommand.CREATE.value,
            target=target,
            requirement=requirement,
            update_mode=None,
            audit_report=None,
            audit_report_path=None,
            strategy=strategy,
            max_tasks=max_tasks,
            output=output,
            executor=executor,
            create_target_was_nonempty=create_target_was_nonempty,
        )

    def update(
        self,
        *,
        path: str,
        update_mode: str,
        requirement: str | None,
        audit_report_path: str | None,
        strategy: str,
        max_tasks: int,
        output: str,
        executor: str,
    ) -> Run:
        self._validate_max_tasks(max_tasks)
        target = self._bootstrap_update_target(path)
        return self._run(
            command=RunCommand.UPDATE.value,
            target=target,
            requirement=requirement,
            update_mode=update_mode,
            audit_report=None,
            audit_report_path=audit_report_path,
            strategy=strategy,
            max_tasks=max_tasks,
            output=output,
            executor=executor,
            create_target_was_nonempty=False,
        )

    def _run(
        self,
        *,
        command: str,
        target: Path,
        requirement: str | None,
        update_mode: str | None,
        audit_report: AuditReport | None,
        audit_report_path: str | None,
        strategy: str,
        max_tasks: int,
        output: str,
        executor: str,
        create_target_was_nonempty: bool,
    ) -> Run:
        git_before = self.git_inspector.inspect(target)
        session_factory = create_session_factory(target)
        run_id = generate_uuid()
        this_run_dir = run_dir(target, run_id)
        this_run_dir.mkdir(parents=True, exist_ok=True)
        progress = ProgressService(run_id, this_run_dir, output)
        progress.emit("RUN_CREATED", f"command={command} path={target}")
        progress.emit("COMMAND_VALIDATED", "path validated")
        self._write_git_snapshot(this_run_dir, "git_before.json", git_before)
        self._emit_git_snapshot(progress, "GIT_PRECHECK", git_before)
        with session_factory() as session:
            run = Run(
                id=run_id,
                command=command,
                update_mode=update_mode,
                path=str(target),
                requirement=requirement,
                audit_report_path=audit_report_path,
                audit_report_summary=None,
                strategy_name=strategy,
                max_tasks=max_tasks,
                executor_type=executor,
            )
            RunRepository(session).add(run)
            session.commit()

            try:
                audit_report = self._validate_project_inputs(
                    command=command,
                    target=target,
                    update_mode=update_mode,
                    requirement=requirement,
                    audit_report_path=audit_report_path,
                    strategy=strategy,
                    executor=executor,
                    create_target_was_nonempty=create_target_was_nonempty,
                )
                if git_before.is_repository and git_before.dirty and self.require_clean_git_worktree:
                    raise ProjectValidationError("Git worktree is dirty and require-clean-git-worktree is enabled")
                project_memory = self._load_project_memory(target)
                if project_memory:
                    progress.emit("MEMORY_LOADED", ".coding-agent/memory.md", payload={"path": ".coding-agent/memory.md"})
                if update_mode:
                    progress.emit("UPDATE_MODE_VALIDATED", update_mode)
                if audit_report:
                    run.audit_report_summary = audit_report.summary
                    (this_run_dir / "audit_report.md").write_text(
                        redact_text(audit_report.raw_content), encoding="utf-8"
                    )
                    progress.emit("AUDIT_REPORT_LOADED", audit_report.summary)
                if requirement:
                    (this_run_dir / "input.md").write_text(redact_text(requirement), encoding="utf-8")
                session.commit()
                return self._plan_and_execute(
                    session=session,
                    run=run,
                    target=target,
                    requirement=requirement,
                    update_mode=update_mode,
                    audit_report=audit_report,
                    strategy=strategy,
                    max_tasks=max_tasks,
                    executor=executor,
                    progress=progress,
                    project_memory=project_memory,
                    initial_git_dirty=git_before.is_repository and git_before.dirty,
                )
            except Exception as exc:
                self._mark_run_failed(
                    session=session,
                    run=run,
                    run_dir_path=this_run_dir,
                    progress=progress,
                    error=exc,
                    project_validation=isinstance(exc, ProjectValidationError),
                )
                return run

    def _plan_and_execute(
        self,
        *,
        session: Session,
        run: Run,
        target: Path,
        requirement: str | None,
        update_mode: str | None,
        audit_report: AuditReport | None,
        strategy: str,
        max_tasks: int,
        executor: str,
        progress: ProgressService,
        project_memory: str,
        initial_git_dirty: bool,
    ) -> Run:
        this_run_dir = run_dir(target, run.id)
        progress.emit("STRATEGY_LOADED", strategy)
        self.state_machine.transition_run(run, RunStatus.PLANNING)
        session.commit()
        plan = self.planning_service.create_plan(
            run_id=run.id,
            command=run.command,
            path=str(target),
            requirement=requirement,
            update_mode=update_mode,
            audit_report=audit_report,
            strategy_name=strategy,
            max_tasks=max_tasks,
            project_memory=project_memory,
        )
        tmp_plan = self.planning_service.write_plan_tmp(plan, this_run_dir)
        tasks = self.task_service.tasks_from_plan(plan, executor_type=executor)
        run.plan_path = os.path.relpath(this_run_dir / "plan.json", target)
        run.total_tasks = len(tasks)
        TaskRepository(session).add_all(tasks)
        session.commit()
        tmp_plan.replace(this_run_dir / "plan.json")
        progress.emit("PLAN_CREATED", f"tasks={len(tasks)}", payload={"tasks": len(tasks)})

        self.state_machine.transition_run(run, RunStatus.RUNNING)
        session.commit()
        self._execute_tasks(session, run, tasks, target, this_run_dir, progress, project_memory)
        git_after = self.git_inspector.inspect(target)
        self._write_git_snapshot(this_run_dir, "git_after.json", git_after)
        self._emit_git_snapshot(progress, "GIT_POSTCHECK", git_after)
        final_tasks = TaskRepository(session).list_by_run(run.id)
        if run.failed_task_ids:
            self.state_machine.transition_run(run, RunStatus.FAILED)
            progress.emit("RUN_FAILED", "one or more tasks failed")
        else:
            if self.commit_on_success:
                # Staging a dirty worktree would also capture changes that existed before this Run.
                # Preserve those user changes rather than guessing which files belong to the Run.
                if initial_git_dirty:
                    commit_result = GitCommitResult(
                        created=False,
                        message="local commit skipped: worktree was dirty before run",
                    )
                else:
                    commit_result = self.git_inspector.commit(target, "coding-agent: completed run")
                (this_run_dir / "git_commit.json").write_text(
                    json.dumps(commit_result.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                progress.emit(
                    "GIT_LOCAL_COMMIT",
                    commit_result.message,
                    payload=commit_result.model_dump(),
                )
                if not commit_result.created and not any(
                    reason in commit_result.message
                    for reason in (
                        "no project changes",
                        "worktree was dirty before run",
                        "target is not a Git repository",
                    )
                ):
                    raise ValidationError(commit_result.message)
            self.state_machine.transition_run(run, RunStatus.SUCCESS)
            progress.emit("RUN_FINISHED", "success")
        report_path = self.report_service.generate(run, final_tasks, this_run_dir)
        session.commit()
        progress.emit("REPORT_CREATED", str(report_path))
        return run

    def _execute_tasks(
        self,
        session: Session,
        run: Run,
        tasks: list[Task],
        target: Path,
        this_run_dir: Path,
        progress: ProgressService,
        project_memory: str,
    ) -> None:
        coding_executor = self.executor or ExecutorFactory.create(run.executor_type)
        reviewer = self.reviewer
        completed = list(run.completed_task_ids or [])
        failed = list(run.failed_task_ids or [])
        completed_context: list[CompletedTaskContext] = []
        skipping = False
        for task in tasks:
            if skipping:
                self.state_machine.transition_task(task, TaskStatus.SKIPPED)
                session.commit()
                continue
            coding_task = CodingTask(
                task_id=task.id,
                order_index=task.order_index,
                title=task.title,
                description=task.description,
                scope=task.scope,
                acceptance_criteria=task.acceptance_criteria,
                verification_commands=task.verification_commands,
            )
            self.state_machine.transition_run(run, RunStatus.RUNNING, current_task_id=task.id)
            self.state_machine.transition_task(task, TaskStatus.RUNNING)
            session.commit()
            progress.emit("TASK_STARTED", task.title, task_id=task.id)
            task_dir = this_run_dir / "tasks" / task.id
            # Preserve every retry without requiring a database schema migration.
            attempt_history: list[dict] = []
            retry_feedback: RetryFeedback | None = None

            for attempt in range(1, self.max_task_attempts + 1):
                if attempt > 1:
                    self.state_machine.transition_task(task, TaskStatus.RUNNING)
                    session.commit()

                attempt_dir = task_dir / f"attempt-{attempt}"
                attempt_dir.mkdir(parents=True, exist_ok=True)
                progress.emit(
                    "TASK_ATTEMPT_STARTED",
                    f"attempt={attempt}/{self.max_task_attempts}",
                    task_id=task.id,
                    payload={"attempt": attempt, "max_attempts": self.max_task_attempts},
                )
                result = self._execute_attempt(
                    coding_executor,
                    coding_task,
                    run_id=run.id,
                    target=target,
                    attempt_dir=attempt_dir,
                    attempt=attempt,
                    retry_feedback=retry_feedback,
                    progress=progress,
                    completed_tasks=completed_context,
                    project_memory=project_memory,
                )
                executor_log = self._ensure_executor_log(result, attempt_dir)
                result.log_path = str(executor_log)
                task.executor_exit_code = result.exit_code
                task.executor_log_path = self._relative_path(executor_log, target)
                task.summary = result.summary
                progress.emit(
                    "TASK_EXECUTED",
                    result.summary,
                    task_id=task.id,
                    payload={"attempt": attempt, "exit_code": result.exit_code},
                )
                self.state_machine.transition_task(task, TaskStatus.REVIEWING)
                session.commit()
                progress.emit(
                    "REVIEW_STARTED",
                    task.title,
                    task_id=task.id,
                    payload={"attempt": attempt},
                )
                review = self._review_attempt(
                    reviewer,
                    coding_task,
                    result,
                    run_id=run.id,
                    target=target,
                    attempt_dir=attempt_dir,
                )
                progress.emit(
                    "REVIEW_FINISHED",
                    review.status,
                    task_id=task.id,
                    payload={"attempt": attempt},
                )

                passed = review.status == ReviewStatus.PASSED.value
                failure_summary = "" if passed else self._failure_summary(result, review)
                outcome = "PASSED" if passed else "RETRYING" if attempt < self.max_task_attempts else "FAILED"
                attempt_history.append(
                    self._attempt_record(
                        attempt=attempt,
                        max_attempts=self.max_task_attempts,
                        result=result,
                        review=review,
                        failure_summary=failure_summary,
                        outcome=outcome,
                        target=target,
                    )
                )
                self._write_attempt_history(task_dir, attempt_history)

                if passed:
                    self.state_machine.transition_task(
                        task,
                        TaskStatus.PASSED,
                        review_status=review.status,
                        review_summary=review.summary,
                        review_findings=list(review.findings),
                        summary=result.summary,
                    )
                    progress.emit(
                        "TASK_ATTEMPT_PASSED",
                        f"attempt={attempt}/{self.max_task_attempts}",
                        task_id=task.id,
                        payload={"attempt": attempt, "max_attempts": self.max_task_attempts},
                    )
                    break

                self.state_machine.update_task_review(
                    task,
                    review_status=review.status,
                    review_summary=review.summary,
                    review_findings=list(review.findings),
                    summary=result.summary,
                )
                progress.emit(
                    "TASK_ATTEMPT_FAILED",
                    f"attempt={attempt}/{self.max_task_attempts} reason={self._failure_kind(result, review)}; "
                    "see task artifacts",
                    task_id=task.id,
                    payload={
                        "attempt": attempt,
                        "max_attempts": self.max_task_attempts,
                        "review_status": review.status,
                        "failure_kind": self._failure_kind(result, review),
                    },
                )
                if attempt < self.max_task_attempts:
                    retry_feedback = self._build_retry_feedback(
                        result,
                        review,
                        attempt_dir,
                        attempt,
                        failure_summary,
                    )
                    progress.emit(
                        "TASK_RETRY_SCHEDULED",
                        f"next_attempt={attempt + 1}/{self.max_task_attempts}",
                        task_id=task.id,
                        payload={"attempt": attempt + 1, "max_attempts": self.max_task_attempts},
                    )
                    session.commit()
                    continue

                self.state_machine.transition_task(
                    task,
                    TaskStatus.FAILED,
                    error_message=failure_summary,
                    review_status=review.status,
                    review_summary=review.summary,
                    review_findings=list(review.findings),
                    summary=result.summary,
                )
                failed.append(task.id)
                skipping = True
                break

            completed.append(task.id)
            if task.status == TaskStatus.PASSED.value:
                completed_context.append(
                    CompletedTaskContext(
                        task_id=task.id,
                        title=task.title,
                        summary=truncate_text(redact_text(task.summary), self.retry_feedback_max_chars),
                        key_files=list(task.scope or []),
                    )
                )
            run.completed_task_ids = completed
            run.failed_task_ids = failed
            session.commit()
            progress.emit("TASK_FINISHED", task.status, task_id=task.id)

    def _execute_attempt(
        self,
        executor: CodingExecutor,
        task: CodingTask,
        *,
        run_id: str,
        target: Path,
        attempt_dir: Path,
        attempt: int,
        retry_feedback: RetryFeedback | None,
        progress: ProgressService,
        completed_tasks: list[CompletedTaskContext],
        project_memory: str,
    ) -> ExecutionResult:
        try:
            return executor.execute(
                task,
                ExecutionContext(
                    run_id=run_id,
                    path=str(target),
                    task_dir=str(attempt_dir),
                    attempt=attempt,
                    max_attempts=self.max_task_attempts,
                    retry_feedback=retry_feedback,
                    completed_tasks=completed_tasks,
                    project_memory=project_memory,
                ),
                on_output=lambda line, task_id=task.task_id: progress.emit(
                    "EXECUTOR_OUTPUT",
                    line[:500],
                    task_id=task_id,
                    payload={"attempt": attempt},
                ),
            )
        except Exception as exc:
            log_path = attempt_dir / "executor.log"
            log_path.write_text(f"Executor exception:\n{exc}\n", encoding="utf-8")
            return ExecutionResult(
                success=False,
                summary="Executor raised an exception",
                error_message=str(exc),
                log_path=str(log_path),
            )

    @staticmethod
    def _review_attempt(
        reviewer: Reviewer,
        task: CodingTask,
        result: ExecutionResult,
        *,
        run_id: str,
        target: Path,
        attempt_dir: Path,
    ) -> ReviewResult:
        try:
            review = reviewer.review(
                task,
                result,
                ReviewContext(run_id=run_id, path=str(target), task_dir=str(attempt_dir)),
            )
            if not result.success and review.status == ReviewStatus.PASSED.value:
                return ReviewResult(
                    status=ReviewStatus.FAILED.value,
                    summary="Executor failed; review cannot pass. See executor.log for details.",
                    findings=[
                        *review.findings,
                        {"kind": "execution_failure", "artifact": "executor.log"},
                    ],
                )
            return review
        except Exception as exc:
            log_path = attempt_dir / "reviewer.log"
            log_path.write_text(f"Reviewer exception:\n{exc}\n", encoding="utf-8")
            return ReviewResult(
                status=ReviewStatus.FAILED.value,
                summary="Reviewer raised an exception. See reviewer.log for details.",
                findings=[{"kind": "reviewer_error", "artifact": "reviewer.log"}],
            )

    @staticmethod
    def _ensure_executor_log(result: ExecutionResult, attempt_dir: Path) -> Path:
        log_path = Path(result.log_path) if result.log_path else attempt_dir / "executor.log"
        if not log_path.is_absolute():
            log_path = attempt_dir / log_path
        attempt_root = attempt_dir.resolve()
        log_path = log_path.resolve()
        try:
            log_path.relative_to(attempt_root)
        except ValueError:
            log_path = attempt_root / "executor.log"
        if log_path.exists():
            return log_path

        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "\n".join(
                [
                    f"summary: {result.summary}",
                    f"exit_code: {result.exit_code}",
                    "stdout:",
                    result.stdout,
                    "stderr:",
                    result.stderr,
                    "error:",
                    result.error_message or "",
                ]
            ),
            encoding="utf-8",
        )
        return log_path

    def _build_retry_feedback(
        self,
        result: ExecutionResult,
        review: ReviewResult,
        attempt_dir: Path,
        attempt: int,
        failure_summary: str,
    ) -> RetryFeedback:
        failure_budget = self.retry_feedback_max_chars // 5
        findings_budget = self.retry_feedback_max_chars // 5
        excerpt_budget = (self.retry_feedback_max_chars - failure_budget - findings_budget) // 3
        executor_log = Path(result.log_path) if result.log_path else None
        verification_log = attempt_dir / "verification.log"
        reviewer_log = attempt_dir / "reviewer.log"
        return RetryFeedback(
            failed_attempt=attempt,
            failure_summary=truncate_text(redact_text(failure_summary), failure_budget),
            executor_log_path=str(executor_log) if executor_log and executor_log.exists() else None,
            executor_log_excerpt=self._read_log_excerpt(executor_log, excerpt_budget),
            verification_log_path=str(verification_log) if verification_log.exists() else None,
            verification_log_excerpt=self._read_log_excerpt(verification_log, excerpt_budget),
            reviewer_log_path=str(reviewer_log) if reviewer_log.exists() else None,
            reviewer_log_excerpt=self._read_log_excerpt(reviewer_log, excerpt_budget),
            review_findings=self._truncate_findings(redact_data(review.findings), findings_budget),
        )

    @staticmethod
    def _failure_summary(result: ExecutionResult, review: ReviewResult) -> str:
        if not result.success and review.status == ReviewStatus.PASSED.value:
            return result.summary or "Executor failed without a summary."
        return review.summary or result.summary or "Task attempt failed without a summary."

    @staticmethod
    def _failure_kind(result: ExecutionResult, review: ReviewResult) -> str:
        if not result.success:
            return "execution"
        if review.status != ReviewStatus.PASSED.value:
            return "review"
        return "unknown"

    @staticmethod
    def _read_log_excerpt(path: Path | None, max_chars: int) -> str:
        if path is None or not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return truncate_text(redact_text(content), max_chars, keep_tail=True)

    @staticmethod
    def _truncate_findings(findings: list[dict], max_chars: int) -> list[dict]:
        serialized = json.dumps(findings, ensure_ascii=False)
        if len(serialized) <= max_chars:
            return list(findings)
        return [{"kind": "review_findings_excerpt", "content": truncate_text(serialized, max_chars)}]

    def _attempt_record(
        self,
        *,
        attempt: int,
        max_attempts: int,
        result: ExecutionResult,
        review: ReviewResult,
        failure_summary: str,
        outcome: str,
        target: Path,
    ) -> dict:
        return {
            "kind": "attempt",
            "attempt": attempt,
            "max_attempts": max_attempts,
            "outcome": outcome,
            "executor_success": result.success,
            "executor_summary": redact_text(result.summary),
            "executor_exit_code": result.exit_code,
            "executor_log_path": RunService._relative_path(result.log_path, target),
            "review_status": review.status,
            "review_summary": redact_text(review.summary),
            "failure_summary": redact_text(failure_summary),
            "review_findings": redact_data(review.findings),
        }

    @staticmethod
    def _write_attempt_history(task_dir: Path, attempts: list[dict]) -> None:
        (task_dir / "attempts.json").write_text(
            json.dumps({"attempts": attempts}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _relative_path(path: str | Path | None, target: Path) -> str | None:
        if path is None:
            return None
        try:
            return os.path.relpath(str(path), target)
        except ValueError:
            return str(path)

    @staticmethod
    def _validate_max_tasks(max_tasks: int) -> None:
        hard_limit = min(settings.hard_max_tasks, HARD_MAX_TASKS)
        if not 1 <= max_tasks <= hard_limit:
            raise UsageError(f"max tasks must be between 1 and {hard_limit}")

    @staticmethod
    def _bootstrap_create_target(path: str) -> tuple[Path, bool]:
        target = ensure_absolute_path(path)
        if target.exists():
            if not target.is_dir():
                raise BootstrapError("create target must be a directory")
            if not os.access(target, os.W_OK | os.X_OK):
                raise BootstrapError("create target directory is not writable")
            # .coding-agent may exist from a previous failed run of this tool; treating it
            # as project content would permanently block retrying create on the same directory.
            harness_entries = {".git", ".coding-agent"}
            return target, any(entry.name not in harness_entries for entry in target.iterdir())

        parent = target.parent
        if not parent.exists() or not parent.is_dir():
            raise BootstrapError("parent directory does not exist")
        if not os.access(parent, os.W_OK | os.X_OK):
            raise BootstrapError("parent directory is not writable")
        try:
            target.mkdir()
        except OSError as exc:
            raise BootstrapError(f"could not create target directory: {exc}") from exc
        if not os.access(target, os.W_OK | os.X_OK):
            raise BootstrapError("create target directory is not writable")
        return target, False

    @staticmethod
    def _bootstrap_update_target(path: str) -> Path:
        target = ensure_absolute_path(path)
        if not target.exists() or not target.is_dir():
            raise BootstrapError("update target directory must exist")
        if not os.access(target, os.W_OK | os.X_OK):
            raise BootstrapError("update target directory is not writable")
        return target

    def _validate_project_inputs(
        self,
        *,
        command: str,
        target: Path,
        update_mode: str | None,
        requirement: str | None,
        audit_report_path: str | None,
        strategy: str,
        executor: str,
        create_target_was_nonempty: bool,
    ) -> AuditReport | None:
        if command == RunCommand.CREATE.value and create_target_was_nonempty:
            raise ProjectValidationError("create target directory must be empty")

        try:
            self.planning_service.strategy_loader.load(strategy)
        except (OSError, ValueError) as exc:
            raise ProjectValidationError(f"strategy validation failed: {exc}") from exc

        if self.executor is None:
            try:
                ExecutorFactory.create(executor)
            except ValidationError as exc:
                raise ProjectValidationError(str(exc)) from exc

        if command != RunCommand.UPDATE.value:
            return None
        if update_mode not in {UpdateMode.REQUIREMENT.value, UpdateMode.AUDIT_REPORT.value}:
            raise ProjectValidationError("update-mode must be requirement or audit-report")
        if update_mode == UpdateMode.REQUIREMENT.value:
            if not requirement or not requirement.strip():
                raise ProjectValidationError("requirement is required for requirement update mode")
            return None
        if not audit_report_path:
            raise ProjectValidationError("audit-report path is required")

        report_path = Path(audit_report_path).expanduser()
        if report_path.suffix.lower() not in {".md", ".txt", ".json"}:
            raise ProjectValidationError("audit-report must be a .md, .txt, or .json file")
        try:
            audit_report = load_audit_report(str(report_path))
        except (OSError, ValueError) as exc:
            raise ProjectValidationError(f"could not load audit-report: {exc}") from exc
        if not audit_report.items:
            raise ProjectValidationError("audit-report contains no valid audit items")
        return audit_report

    def _mark_run_failed(
        self,
        *,
        session: Session,
        run: Run,
        run_dir_path: Path,
        progress: ProgressService,
        error: Exception,
        project_validation: bool,
    ) -> None:
        if run.status not in {RunStatus.SUCCESS.value, RunStatus.FAILED.value, RunStatus.CANCELED.value}:
            self.state_machine.transition_run(run, RunStatus.FAILED, error_message=str(error))
        session.commit()
        progress.emit("PROJECT_VALIDATION_FAILED" if project_validation else "RUN_FAILED", str(error))
        try:
            tasks = TaskRepository(session).list_by_run(run.id)
            report_path = self.report_service.generate(run, tasks, run_dir_path)
            session.commit()
            progress.emit("REPORT_CREATED", str(report_path))
        except Exception as report_error:
            progress.emit("REPORT_FAILED", str(report_error))

    @staticmethod
    def _load_project_memory(target: Path) -> str:
        memory_path = target / ".coding-agent" / "memory.md"
        if not memory_path.exists():
            return ""
        try:
            return memory_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ProjectValidationError(f"could not read project memory: {exc}") from exc

    @staticmethod
    def _write_git_snapshot(this_run_dir: Path, name: str, snapshot: GitSnapshot) -> None:
        (this_run_dir / name).write_text(
            json.dumps(snapshot.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _emit_git_snapshot(self, progress: ProgressService, event_type: str, snapshot: GitSnapshot) -> None:
        if not snapshot.is_repository:
            progress.emit(event_type, "not a Git repository", payload=snapshot.model_dump())
            return
        summary = truncate_text(snapshot.diff_summary, 500).replace("\n", " | ")
        message = f"branch={snapshot.branch or 'detached'} dirty={snapshot.dirty}; diff={summary}"
        progress.emit(event_type, message, payload=snapshot.model_dump())
        if snapshot.dirty:
            disposition = (
                "Git worktree has project changes; require-clean-git-worktree will fail the Run."
                if self.require_clean_git_worktree
                else "Git worktree has project changes; continuing because clean-worktree enforcement is disabled."
            )
            progress.emit(
                "GIT_DIRTY_WARNING",
                disposition,
                payload={"branch": snapshot.branch, "affected_files": snapshot.affected_files},
            )
