from __future__ import annotations

import typer

from app.core.config import settings
from app.core.limits import HARD_MAX_TASK_ATTEMPTS, HARD_MAX_TASKS

# 验证最大任务数
def validate_max_tasks(value: int) -> int:
    hard_limit = min(settings.hard_max_tasks, HARD_MAX_TASKS)
    if not 1 <= value <= hard_limit:
        raise typer.BadParameter(f"must be between 1 and {hard_limit}")
    return value


# 验证最大尝试次数
def validate_max_attempts(value: int) -> int:
    if not 1 <= value <= HARD_MAX_TASK_ATTEMPTS:
        raise typer.BadParameter(f"must be between 1 and {HARD_MAX_TASK_ATTEMPTS}")
    return value
