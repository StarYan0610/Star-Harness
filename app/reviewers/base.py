from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.task import ExecutionResult, ReviewContext, ReviewResult, CodingTask


class Reviewer(ABC):
    @abstractmethod
    def review(self, task: CodingTask, result: ExecutionResult, context: ReviewContext) -> ReviewResult:
        raise NotImplementedError
