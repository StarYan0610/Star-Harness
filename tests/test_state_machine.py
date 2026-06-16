from app.domain.enums import RunStatus, TaskStatus
from app.domain.state_machine import WorkflowStateMachine
from app.models.run import Run
from app.models.task import Task


def test_run_state_machine_success_path():
    run = Run(
        id="550e8400-e29b-41d4-a716-446655440000",
        command="create",
        path="/tmp/demo",
        strategy_name="skeleton-first",
        max_tasks=3,
        executor_type="codex",
    )
    sm = WorkflowStateMachine()
    sm.transition_run(run, RunStatus.PLANNING)
    sm.transition_run(run, RunStatus.RUNNING)
    sm.transition_run(run, RunStatus.SUCCESS)
    assert run.status == RunStatus.SUCCESS


def test_task_state_machine_success_path():
    task = Task(
        id="1f5d4b25-1d0e-4910-9d26-14c0d56e3c21",
        run_id="550e8400-e29b-41d4-a716-446655440000",
        title="Task",
        description="Desc",
        order_index=1,
        executor_type="codex",
    )
    sm = WorkflowStateMachine()
    sm.transition_task(task, TaskStatus.RUNNING)
    sm.transition_task(task, TaskStatus.REVIEWING)
    sm.transition_task(task, TaskStatus.PASSED, review_status="PASSED")
    assert task.status == TaskStatus.PASSED
    assert task.review_status == "PASSED"


def test_task_state_machine_allows_retry_after_review_failure():
    task = Task(
        id="1f5d4b25-1d0e-4910-9d26-14c0d56e3c21",
        run_id="550e8400-e29b-41d4-a716-446655440000",
        title="Task",
        description="Desc",
        order_index=1,
        executor_type="codex",
    )
    sm = WorkflowStateMachine()

    sm.transition_task(task, TaskStatus.RUNNING)
    sm.transition_task(task, TaskStatus.REVIEWING)
    sm.transition_task(task, TaskStatus.RUNNING)

    assert task.status == TaskStatus.RUNNING
