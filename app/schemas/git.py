from __future__ import annotations

from pydantic import BaseModel, Field


class GitSnapshot(BaseModel):
    is_repository: bool
    branch: str | None = None
    dirty: bool = False
    diff_summary: str = ""
    affected_files: list[str] = Field(default_factory=list)
    files_truncated: bool = False


class GitCommitResult(BaseModel):
    created: bool
    commit_id: str | None = None
    message: str = ""
