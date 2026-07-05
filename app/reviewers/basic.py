from __future__ import annotations

from app.domain.enums import ReviewStatus
from app.reviewers.base import Reviewer
from app.schemas.task import CodingTask, ExecutionResult, ReviewContext, ReviewResult


class BasicReviewer(Reviewer):
    def review(self, task: CodingTask, result: ExecutionResult, context: ReviewContext) -> ReviewResult:
        if result.success and result.summary.strip():
            return ReviewResult(status=ReviewStatus.PASSED.value, summary="Executor completed successfully")

        if not result.success:
            reason = "executor returned an unsuccessful result"
        else:
            reason = "executor returned no non-empty summary"
        return ReviewResult(
            status=ReviewStatus.FAILED.value,
            summary=f"Executor basic check failed: {reason}. See executor.log for details.",
            findings=[{"kind": "basic_check", "title": task.title, "message": reason}],
        )
