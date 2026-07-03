from __future__ import annotations

from app.core.config import settings
from app.executors.cli import StreamingCliExecutor
from app.schemas.task import CodingTask, CompletedTaskContext, RetryFeedback

# Camel-case values are what the Claude CLI accepts (`claude --help`, 2.1.x);
# validated here so a typo in CLAUDE_PERMISSION_MODE fails the run up front
# instead of inside every task attempt.
CLAUDE_PERMISSION_MODES = {
    "acceptEdits",
    "auto",
    "bypassPermissions",
    "manual",
    "dontAsk",
    "plan",
}


class ClaudeExecutor(StreamingCliExecutor):
    display_name = "Claude"

    def __init__(
        self,
        command: str | None = None,
        timeout_seconds: float | None = None,
        permission_mode: str | None = None,
    ):
        super().__init__(command or settings.claude_command, timeout_seconds)
        self.permission_mode = permission_mode or settings.claude_permission_mode
        if self.permission_mode not in CLAUDE_PERMISSION_MODES:
            raise ValueError(
                f"unsupported Claude permission mode: {self.permission_mode}; "
                f"expected one of {sorted(CLAUDE_PERMISSION_MODES)}"
            )

    def build_command(
        self,
        task: CodingTask,
        retry_feedback: RetryFeedback | None = None,
        *,
        completed_tasks: list[CompletedTaskContext] | None = None,
        project_memory: str = "",
    ) -> list[str]:
        # -p (print) runs headless in the subprocess CWD; --verbose surfaces
        # whatever intermediate output print mode provides (text mode may still
        # emit only the final result — the timeout watchdog covers hangs).
        # acceptEdits auto-approves file edits only — command execution stays
        # gated, mirroring the workspace-write stance of the Codex sandbox.
        return [
            self.command,
            "-p",
            "--output-format",
            "text",
            "--verbose",
            "--permission-mode",
            self.permission_mode,
            self.build_prompt(
                task,
                retry_feedback,
                completed_tasks=completed_tasks,
                project_memory=project_memory,
            ),
        ]
