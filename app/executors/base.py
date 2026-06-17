from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from app.schemas.task import CodingTask, ExecutionContext, ExecutionResult


class CodingExecutor(ABC):
    @abstractmethod
    def execute(
        self,
        task: CodingTask,
        context: ExecutionContext,
        on_output: Callable[[str], None] | None = None,
    ) -> ExecutionResult:
        raise NotImplementedError
