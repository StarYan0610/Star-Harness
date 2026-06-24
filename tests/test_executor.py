from app.executors.codex import CodexExecutor
from app.schemas.task import CodingTask, RetryFeedback


def test_codex_executor_builds_command():
    task = CodingTask(
        task_id="1f5d4b25-1d0e-4910-9d26-14c0d56e3c21",
        order_index=1,
        title="实现功能",
        description="添加邮箱校验",
        scope=["app"],
        acceptance_criteria=["校验非法邮箱"],
        verification_commands=["pytest"],
    )
    command = CodexExecutor(command="codex").build_command(task)
    assert command[0] == "codex"
    assert command[1] == "exec"
    assert "--skip-git-repo-check" in command
    assert "--color" in command
    assert "--sandbox" in command
    assert "添加邮箱校验" in command[-1]
    assert "校验非法邮箱" in command[-1]


def test_codex_executor_includes_retry_feedback_in_prompt():
    task = CodingTask(
        task_id="1f5d4b25-1d0e-4910-9d26-14c0d56e3c21",
        order_index=1,
        title="实现功能",
        description="添加邮箱校验",
    )
    feedback = RetryFeedback(
        failed_attempt=1,
        failure_summary="命令验收失败",
        executor_log_path=".coding-agent/runs/run/tasks/task/attempt-1/executor.log",
        executor_log_excerpt="first attempt output",
        review_findings=[{"kind": "verification_command", "exit_code": 1}],
    )

    prompt = CodexExecutor(command="codex").build_prompt(task, feedback)

    assert "上次失败反馈" in prompt
    assert "命令验收失败" in prompt
    assert "first attempt output" in prompt
    assert "verification_command" in prompt
