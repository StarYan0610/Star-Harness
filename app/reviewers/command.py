from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import TextIO

from app.core.config import settings
from app.domain.enums import ReviewStatus
from app.reviewers.base import Reviewer
from app.reviewers.basic import BasicReviewer
from app.schemas.task import CodingTask, ExecutionResult, ReviewContext, ReviewResult


class CommandReviewer(Reviewer):
    """Run a task's configured verification commands after the basic check passes."""

    def __init__(self, timeout_seconds: float | None = None):
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.verification_timeout_seconds
        if self.timeout_seconds <= 0:
            raise ValueError("verification command timeout must be greater than zero")
        self.basic_reviewer = BasicReviewer()

    def review(self, task: CodingTask, result: ExecutionResult, context: ReviewContext) -> ReviewResult:
        basic_review = self.basic_reviewer.review(task, result, context)
        if basic_review.status != ReviewStatus.PASSED.value:
            if not task.verification_commands:
                return ReviewResult(
                    status=basic_review.status,
                    summary=f"未配置命令验收，仅基础检查：{basic_review.summary}",
                    findings=basic_review.findings,
                )
            return basic_review

        if not task.verification_commands:
            return ReviewResult(
                status=ReviewStatus.PASSED.value,
                summary="未配置命令验收，仅基础检查。",
                findings=[{"kind": "basic_check", "status": ReviewStatus.PASSED.value}],
            )

        task_dir = self._task_dir(task, context)
        task_dir.mkdir(parents=True, exist_ok=True)
        log_path = task_dir / "verification.log"
        findings: list[dict] = []

        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            for index, command in enumerate(task.verification_commands, start=1):
                if not command.strip():
                    self._write_invalid_command(log_file, index)
                    findings.append(self._finding(index, ReviewStatus.FAILED.value, None))
                    return self._failed_result(index, "is empty", findings)

                try:
                    # start_new_session so a timeout can kill the whole process group;
                    # killing only the shell would leave the actual command running and leaking.
                    process = subprocess.Popen(
                        command,
                        shell=True,
                        cwd=context.path,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        start_new_session=True,
                    )
                except OSError as exc:
                    self._write_command_error(log_file, command, str(exc))
                    findings.append(self._finding(index, ReviewStatus.FAILED.value, None))
                    return self._failed_result(index, "could not be started", findings)

                try:
                    stdout, stderr = process.communicate(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    self._kill_process_group(process)
                    stdout, stderr = process.communicate()
                    self._write_command_output(
                        log_file,
                        command,
                        stdout=self._as_text(stdout),
                        stderr=self._as_text(stderr),
                        timeout=True,
                    )
                    findings.append(self._finding(index, ReviewStatus.FAILED.value, None, timed_out=True))
                    return self._failed_result(index, f"timed out after {self.timeout_seconds:g}s", findings)
                completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

                self._write_command_output(
                    log_file,
                    command,
                    stdout=self._as_text(completed.stdout),
                    stderr=self._as_text(completed.stderr),
                    return_code=completed.returncode,
                )
                status = ReviewStatus.PASSED.value if completed.returncode == 0 else ReviewStatus.FAILED.value
                findings.append(self._finding(index, status, completed.returncode))
                if completed.returncode != 0:
                    return self._failed_result(index, f"exited with code {completed.returncode}", findings)

        return ReviewResult(
            status=ReviewStatus.PASSED.value,
            summary=f"命令验收通过：已执行 {len(task.verification_commands)} 条验证命令。",
            findings=findings,
        )

    @staticmethod
    def _kill_process_group(process: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            process.kill()

    @staticmethod
    def _task_dir(task: CodingTask, context: ReviewContext) -> Path:
        if context.task_dir:
            return Path(context.task_dir)
        return Path(context.path) / ".coding-agent" / "runs" / context.run_id / "tasks" / task.task_id

    @staticmethod
    def _as_text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @staticmethod
    def _finding(
        index: int,
        status: str,
        exit_code: int | None,
        *,
        timed_out: bool = False,
    ) -> dict:
        return {
            "kind": "verification_command",
            "index": index,
            "status": status,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "artifact": "verification.log",
        }

    @staticmethod
    def _write_invalid_command(log_file: TextIO, index: int) -> None:
        log_file.write(f"verification command {index} is empty\n")

    @staticmethod
    def _write_command_error(log_file: TextIO, command: str, error: str) -> None:
        log_file.write(f"$ {command}\n")
        log_file.write(f"could not start command: {error}\n\n")

    @staticmethod
    def _write_command_output(
        log_file: TextIO,
        command: str,
        *,
        stdout: str,
        stderr: str,
        return_code: int | None = None,
        timeout: bool = False,
    ) -> None:
        log_file.write(f"$ {command}\n")
        if timeout:
            log_file.write("result: timed out\n")
        else:
            log_file.write(f"exit_code: {return_code}\n")
        log_file.write("stdout:\n")
        log_file.write(stdout)
        if stdout and not stdout.endswith("\n"):
            log_file.write("\n")
        log_file.write("stderr:\n")
        log_file.write(stderr)
        if stderr and not stderr.endswith("\n"):
            log_file.write("\n")
        log_file.write("\n")
        log_file.flush()

    @staticmethod
    def _failed_result(index: int, reason: str, findings: list[dict]) -> ReviewResult:
        return ReviewResult(
            status=ReviewStatus.FAILED.value,
            summary=f"命令验收失败：第 {index} 条验证命令 {reason}。详见任务产物 verification.log。",
            findings=findings,
        )
