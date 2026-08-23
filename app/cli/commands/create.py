from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape

from app.cli.validation import validate_max_attempts, validate_max_tasks
from app.core.config import settings
from app.core.exceptions import CodingAgentError, UsageError
from app.domain.enums import RunStatus
from app.services.run_service import RunService
from app.utils.redaction import redact_text

app = typer.Typer()
console = Console()

# 创建项目
@app.command("create")
def create_project(
    path: str = typer.Option(..., "--path"),
    requirement: str = typer.Option(..., "--requirement"),
    strategy: str = typer.Option(settings.default_strategy, "--strategy"),
    max_tasks: int = typer.Option(settings.default_max_tasks, "--max-tasks", callback=validate_max_tasks),
    max_attempts: int = typer.Option(settings.max_task_attempts, "--max-attempts", callback=validate_max_attempts),
    require_clean_git_worktree: bool = typer.Option(
        settings.require_clean_git_worktree,
        "--require-clean-git-worktree",
        help="Fail the Run if an existing Git worktree has project changes.",
    ),
    commit_on_success: bool = typer.Option(
        settings.commit_on_success,
        "--commit-on-success",
        help="Create one local commit after a successful Run; never pushes.",
    ),
    output: str = typer.Option(settings.default_output_format, "--output"),
    executor: str = typer.Option(settings.default_executor, "--executor"),
) -> None:
    try:
        run = RunService(
            max_task_attempts=max_attempts,
            require_clean_git_worktree=require_clean_git_worktree,
            commit_on_success=commit_on_success,
        ).create(
            path=path,
            requirement=requirement,
            strategy=strategy,
            max_tasks=max_tasks,
            output=output,
            executor=executor,
        )
        console.print(f"\nRun ID: {run.id}")
        console.print(f"Status: {run.status}")
        console.print(f"Report saved to: .coding-agent/runs/{run.id}/report.md")
        if run.status != RunStatus.SUCCESS.value:
            raise typer.Exit(code=1)
    except UsageError as exc:
        console.print(f"[red]Error:[/red] {escape(redact_text(exc))}")
        raise typer.Exit(code=2) from exc
    except CodingAgentError as exc:
        console.print(f"[red]Error:[/red] {escape(redact_text(exc))}")
        raise typer.Exit(code=1) from exc
