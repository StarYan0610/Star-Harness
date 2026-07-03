import pytest

from app.core.exceptions import ValidationError
from app.executors.claude import ClaudeExecutor
from app.executors.codex import CodexExecutor
from app.executors.factory import ExecutorFactory
from app.schemas.task import CodingTask, RetryFeedback


def _coding_task() -> CodingTask:
    return CodingTask(
        task_id="1f5d4b25-1d0e-4910-9d26-14c0d56e3c21",
        order_index=1,
        title="实现功能",
        description="添加邮箱校验",
        scope=["app"],
        acceptance_criteria=["校验非法邮箱"],
        verification_commands=["python3 -m pytest"],
    )


def test_claude_executor_builds_headless_command():
    command = ClaudeExecutor(command="claude").build_command(_coding_task())

    assert command[0] == "claude"
    assert command[1] == "-p"
    assert "--output-format" in command
    assert command[command.index("--output-format") + 1] == "text"
    assert "--verbose" in command
    assert "--permission-mode" in command
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    assert "添加邮箱校验" in command[-1]
    assert "校验非法邮箱" in command[-1]


def test_claude_executor_prompt_matches_codex_prompt():
    task = _coding_task()
    feedback = RetryFeedback(failed_attempt=1, failure_summary="命令验收失败")

    claude_prompt = ClaudeExecutor(command="claude").build_prompt(task, feedback)
    codex_prompt = CodexExecutor(command="codex").build_prompt(task, feedback)

    assert claude_prompt == codex_prompt
    assert "上次失败反馈" in claude_prompt


def test_claude_executor_rejects_unknown_permission_mode():
    with pytest.raises(ValueError, match="unsupported Claude permission mode"):
        ClaudeExecutor(command="claude", permission_mode="yolo")


def test_claude_executor_accepts_bypass_permissions_mode():
    executor = ClaudeExecutor(command="claude", permission_mode="bypassPermissions")

    command = executor.build_command(_coding_task())

    assert command[command.index("--permission-mode") + 1] == "bypassPermissions"


def test_executor_factory_creates_claude_executor():
    executor = ExecutorFactory.create("claude")

    assert isinstance(executor, ClaudeExecutor)


def test_executor_factory_wraps_invalid_claude_config(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "claude_permission_mode", "invalid-mode")

    with pytest.raises(ValidationError, match="unsupported Claude permission mode"):
        ExecutorFactory.create("claude")


def test_executor_factory_still_rejects_unknown_executor():
    with pytest.raises(ValidationError, match="unsupported executor"):
        ExecutorFactory.create("gemini")
