from __future__ import annotations

from app.core.config import settings
from app.executors.cli import StreamingCliExecutor
from app.schemas.task import CodingTask, CompletedTaskContext, RetryFeedback


class CodexExecutor(StreamingCliExecutor):
    display_name = "Codex"

    def __init__(self, command: str | None = None, timeout_seconds: float | None = None):
        super().__init__(command or settings.codex_command, timeout_seconds)

    def build_command(
        self,
        task: CodingTask,
        retry_feedback: RetryFeedback | None = None,
        *,
        completed_tasks: list[CompletedTaskContext] | None = None,
        project_memory: str = "",
    ) -> list[str]:
        return [
            self.command,
            "exec",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--sandbox",
            "workspace-write",
            self.build_prompt(
                task,
                retry_feedback,
                completed_tasks=completed_tasks,
                project_memory=project_memory,
            ),
        ]
