from __future__ import annotations

from pydantic import BaseModel, Field


class CodingTask(BaseModel):
    task_id: str
    order_index: int
    title: str
    description: str
    scope: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)


class RetryFeedback(BaseModel):
    failed_attempt: int
    failure_summary: str
    executor_log_path: str | None = None
    executor_log_excerpt: str = ""
    verification_log_path: str | None = None
    verification_log_excerpt: str = ""
    reviewer_log_path: str | None = None
    reviewer_log_excerpt: str = ""
    review_findings: list[dict] = Field(default_factory=list)


class CompletedTaskContext(BaseModel):
    task_id: str
    title: str
    summary: str
    key_files: list[str] = Field(default_factory=list)


class ExecutionContext(BaseModel):
    run_id: str
    path: str
    task_dir: str
    attempt: int = 1
    max_attempts: int = 1
    retry_feedback: RetryFeedback | None = None
    completed_tasks: list[CompletedTaskContext] = Field(default_factory=list)
    project_memory: str = ""


class ExecutionResult(BaseModel):
    success: bool
    summary: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None
    log_path: str | None = None


class ReviewContext(BaseModel):
    run_id: str
    path: str
    task_dir: str | None = None


class ReviewResult(BaseModel):
    status: str
    summary: str
    findings: list[dict] = Field(default_factory=list)
