from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.executors.base import CodingExecutor
from app.executors.claude import ClaudeExecutor
from app.executors.codex import CodexExecutor


class ExecutorFactory:
    @staticmethod
    def create(name: str | None = None) -> CodingExecutor:
        executor_name = (name or settings.default_executor).strip().lower()
        if executor_name == "codex":
            return CodexExecutor()
        if executor_name == "claude":
            try:
                return ClaudeExecutor()
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        raise ValidationError(f"unsupported executor: {executor_name or '<empty>'}")
