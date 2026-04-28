from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.limits import HARD_MAX_TASKS


class Settings(BaseSettings):
    app_env: str = "local"
    database_url: str = "sqlite:///./.coding-agent/coding-agent.db"
    default_executor: str = "codex"
    default_planner: str = "simple"
    default_reviewer: str = "command"
    default_strategy: str = "skeleton-first"
    default_max_tasks: int = 6
    hard_max_tasks: int = HARD_MAX_TASKS
    max_task_attempts: int = 2
    retry_feedback_max_chars: int = 10000
    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 60.0
    planner_temperature: float = 0.1
    codex_command: str = "codex"
    claude_command: str = "claude"
    claude_permission_mode: str = "acceptEdits"
    executor_timeout_seconds: float = 3600.0
    verification_timeout_seconds: float = 300.0
    require_clean_git_worktree: bool = False
    commit_on_success: bool = False
    default_output_format: str = "human"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
