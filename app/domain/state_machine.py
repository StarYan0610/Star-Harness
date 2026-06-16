from __future__ import annotations

from app.core.exceptions import StateTransitionError
from app.core.time import naive_utcnow
from app.domain.enums import RunStatus, TaskStatus
from app.models.run import Run
from app.models.task import Task


class WorkflowStateMachine:
    # 运行状态
    _run_transitions = {
        RunStatus.PENDING: {RunStatus.PLANNING, RunStatus.CANCELED, RunStatus.FAILED},
        RunStatus.PLANNING: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELED},
        RunStatus.RUNNING: {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.CANCELED},
        RunStatus.SUCCESS: set(),
        RunStatus.FAILED: set(),
        RunStatus.CANCELED: set(),
    }
    # 任务状态
    _task_transitions = {
        TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.SKIPPED, TaskStatus.FAILED},
        TaskStatus.RUNNING: {TaskStatus.REVIEWING, TaskStatus.FAILED},
        TaskStatus.REVIEWING: {TaskStatus.RUNNING, TaskStatus.PASSED, TaskStatus.FAILED},
        TaskStatus.PASSED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.SKIPPED: set(),
    }

    def transition_run(
        self,
        run: Run,
        target: RunStatus,
        *,
        current_task_id: str | None = None,
        completed_task_ids: list[str] | None = None,
        failed_task_ids: list[str] | None = None,
        error_message: str | None = None,
    ) -> Run:
        current = RunStatus(run.status or RunStatus.PENDING.value)
        if target != current and target not in self._run_transitions[current]:
            raise StateTransitionError(f"illegal run transition: {current} -> {target}")
        run.status = target.value
        if target in {RunStatus.PLANNING, RunStatus.RUNNING} and run.started_at is None:
            run.started_at = naive_utcnow()
        if target in {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.CANCELED}:
            run.finished_at = naive_utcnow()
        if current_task_id is not None:
            run.current_task_id = current_task_id
        if completed_task_ids is not None:
            run.completed_task_ids = completed_task_ids
        if failed_task_ids is not None:
            run.failed_task_ids = failed_task_ids
        if error_message is not None:
            run.error_message = error_message
        run.updated_at = naive_utcnow()
        return run

    def transition_task(
        self,
        task: Task,
        target: TaskStatus,
        *,
        error_message: str | None = None,
        summary: str | None = None,
        review_status: str | None = None,
        review_summary: str | None = None,
        review_findings: list[dict] | None = None,
    ) -> Task:
        current = TaskStatus(task.status or TaskStatus.PENDING.value)
        if target != current and target not in self._task_transitions[current]:
            raise StateTransitionError(f"illegal task transition: {current} -> {target}")
        task.status = target.value
        if target == TaskStatus.RUNNING and task.started_at is None:
            task.started_at = naive_utcnow()
        if target in {TaskStatus.PASSED, TaskStatus.FAILED, TaskStatus.SKIPPED}:
            task.finished_at = naive_utcnow()
        if error_message is not None:
            task.error_message = error_message
        if summary is not None:
            task.summary = summary
        if review_status is not None:
            task.review_status = review_status
        if review_summary is not None:
            task.review_summary = review_summary
        if review_findings is not None:
            task.review_findings = review_findings
        task.updated_at = naive_utcnow()
        return task

    def update_task_review(
        self,
        task: Task,
        *,
        review_status: str,
        review_summary: str,
        review_findings: list[dict],
        summary: str | None = None,
    ) -> Task:
        """Record a completed review without disguising it as a state transition."""
        current = TaskStatus(task.status or TaskStatus.PENDING.value)
        if current != TaskStatus.REVIEWING:
            raise StateTransitionError(f"task review metadata requires REVIEWING status, got {current}")
        task.review_status = review_status
        task.review_summary = review_summary
        task.review_findings = review_findings
        if summary is not None:
            task.summary = summary
        task.updated_at = naive_utcnow()
        return task
