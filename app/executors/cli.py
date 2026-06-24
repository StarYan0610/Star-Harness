from __future__ import annotations

import os
import signal
import subprocess
import threading
from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path

from app.core.config import settings
from app.executors.base import CodingExecutor
from app.schemas.task import CodingTask, CompletedTaskContext, ExecutionContext, ExecutionResult, RetryFeedback
from app.utils.redaction import redact_data, redact_text

# 流式 CLI 执行器
class StreamingCliExecutor(CodingExecutor):
    """Shared behavior for executors that drive an external coding CLI.

    Subclasses provide the concrete argv via build_command; prompt building,
    line-streamed logging, and process-group timeout handling are identical
    across CLIs and live here.
    """

    display_name = "CLI"

    def __init__(self, command: str, timeout_seconds: float | None = None):
        self.command = command
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.executor_timeout_seconds
        if self.timeout_seconds <= 0:
            raise ValueError("executor timeout must be greater than zero")

    # 构建命令
    @abstractmethod
    def build_command(
        self,
        task: CodingTask,
        retry_feedback: RetryFeedback | None = None,
        *,
        completed_tasks: list[CompletedTaskContext] | None = None,
        project_memory: str = "",
    ) -> list[str]:
        raise NotImplementedError

    # 构建提示
    def build_prompt(
        self,
        task: CodingTask,
        retry_feedback: RetryFeedback | None = None,
        *,
        completed_tasks: list[CompletedTaskContext] | None = None,
        project_memory: str = "",
    ) -> str:
        criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria)
        scope = "\n".join(f"- {item}" for item in task.scope)
        retry_context = self._retry_context(retry_feedback)
        run_context = self._run_context(completed_tasks or [], project_memory)
        return (
            f"请完成以下编码任务。\n\n"
            f"标题：{task.title}\n\n"
            f"说明：{task.description}\n\n"
            f"范围：\n{scope or '- 未指定'}\n\n"
            f"验收标准：\n{criteria or '- 未指定'}\n\n"
            f"{run_context}"
            f"{retry_context}"
            f"禁止事项：不要做无关重构，不要自动提交 git commit。"
        )

    # 执行任务
    def execute(
        self,
        task: CodingTask,
        context: ExecutionContext,
        on_output: Callable[[str], None] | None = None,
    ) -> ExecutionResult:
        Path(context.task_dir).mkdir(parents=True, exist_ok=True)
        log_path = Path(context.task_dir) / "executor.log"
        command = self.build_command(
            task,
            context.retry_feedback,
            completed_tasks=context.completed_tasks,
            project_memory=context.project_memory,
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=context.path,
                text=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                start_new_session=True,
            )
            timed_out = threading.Event()

            def _kill_on_timeout() -> None:
                timed_out.set()
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass

            watchdog = threading.Timer(self.timeout_seconds, _kill_on_timeout)
            watchdog.start()
            output_lines: list[str] = []
            try:
                with log_path.open("w", encoding="utf-8") as log_file:
                    log_file.write(f"$ {' '.join(command)}\n\n")
                    assert process.stdout is not None
                    for line in process.stdout:
                        output_lines.append(line)
                        log_file.write(line)
                        log_file.flush()
                        if on_output:
                            on_output(line.rstrip())
                    return_code = process.wait()
            finally:
                watchdog.cancel()

            stdout = "".join(output_lines)
            if timed_out.is_set():
                message = f"{self.display_name} execution timed out after {self.timeout_seconds:g}s"
                with log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(f"\n{message}\n")
                return ExecutionResult(
                    success=False,
                    summary=message,
                    exit_code=return_code,
                    stdout=stdout,
                    stderr="",
                    error_message=message,
                    log_path=str(log_path),
                )
            return ExecutionResult(
                success=return_code == 0,
                summary=(
                    f"{self.display_name} execution completed"
                    if return_code == 0
                    else f"{self.display_name} execution failed"
                ),
                exit_code=return_code,
                stdout=stdout,
                stderr="",
                error_message=None if return_code == 0 else stdout,
                log_path=str(log_path),
            )
        except FileNotFoundError as exc:
            message = f"{self.display_name} command not found: {self.command}"
            log_path.write_text(message, encoding="utf-8")
            return ExecutionResult(success=False, summary=message, error_message=str(exc), log_path=str(log_path))

    @staticmethod
    def _retry_context(retry_feedback: RetryFeedback | None) -> str:
        if retry_feedback is None:
            return ""

        lines = [
            f"这是对第 {retry_feedback.failed_attempt} 次失败尝试的修复。",
            f"失败摘要：{redact_text(retry_feedback.failure_summary)}",
        ]
        if retry_feedback.executor_log_path:
            lines.append(f"执行器日志：{retry_feedback.executor_log_path}")
        if retry_feedback.executor_log_excerpt:
            lines.append(f"执行器日志摘录：\n{redact_text(retry_feedback.executor_log_excerpt)}")
        if retry_feedback.verification_log_path:
            lines.append(f"验证日志：{retry_feedback.verification_log_path}")
        if retry_feedback.verification_log_excerpt:
            lines.append(f"验证日志摘录：\n{redact_text(retry_feedback.verification_log_excerpt)}")
        if retry_feedback.reviewer_log_path:
            lines.append(f"审查器日志：{retry_feedback.reviewer_log_path}")
        if retry_feedback.reviewer_log_excerpt:
            lines.append(f"审查器日志摘录：\n{redact_text(retry_feedback.reviewer_log_excerpt)}")
        if retry_feedback.review_findings:
            lines.append(f"上次审查发现：{redact_data(retry_feedback.review_findings)}")
        return "上次失败反馈：\n" + "\n".join(f"- {line}" for line in lines) + "\n\n"

    @staticmethod
    def _run_context(completed_tasks: list[CompletedTaskContext], project_memory: str) -> str:
        lines: list[str] = []
        if project_memory:
            lines.append(f"项目只读约定：\n{project_memory}")
        if completed_tasks:
            task_lines = []
            for completed in completed_tasks:
                files = ", ".join(completed.key_files) or "未记录"
                task_lines.append(f"- {completed.title}: {completed.summary}；关键文件：{files}")
            lines.append("本 Run 已完成任务：\n" + "\n".join(task_lines))
        return "\n\n".join(lines) + ("\n\n" if lines else "")
