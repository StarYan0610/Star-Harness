from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.reviewers.base import Reviewer
from app.reviewers.basic import BasicReviewer
from app.reviewers.command import CommandReviewer


class ReviewerFactory:
    @staticmethod
    def create(name: str | None = None) -> Reviewer:
        reviewer_name = (name or settings.default_reviewer).strip().lower()
        if reviewer_name == "basic":
            return BasicReviewer()
        if reviewer_name == "command":
            return CommandReviewer()
        raise ValidationError(f"unsupported reviewer: {reviewer_name or '<empty>'}")
