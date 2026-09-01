from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape

from app.core.paths import ensure_absolute_path
from app.core.exceptions import CodingAgentError
from app.db.session import open_existing_session_factory
from app.repositories.run_repository import RunRepository
from app.repositories.task_repository import TaskRepository
from app.utils.redaction import redact_text

app = typer.Typer()
console = Console()

# 查看运行状态
@app.command("status")
def status(path: str = typer.Option(..., "--path"), run_id: str = typer.Option(..., "--run-id")) -> None:
    try:
        # 确保路径存在且为目录
        target = ensure_absolute_path(path)
        if not target.exists() or not target.is_dir():
            raise CodingAgentError("project directory must exist")
        # 打开现有会话工厂
        session_factory = open_existing_session_factory(target)
        with session_factory() as session:
            # 获取运行
            run = RunRepository(session).get(run_id)
            if not run:
                console.print(f"[red]run not found:[/red] {run_id}")
                raise typer.Exit(code=1)
            tasks = TaskRepository(session).list_by_run(run_id)
            console.print(f"Run: {run.id}")
            console.print(f"Requirement: {escape(redact_text(run.requirement))}")
            console.print(f"Status: {run.status}")
            console.print(f"Progress: {len(run.completed_task_ids or [])}/{run.total_tasks}")
            console.print(f"Current Task: {run.current_task_id or '-'}")
            console.print("Completed Tasks:")
            for task_id in run.completed_task_ids or []:
                console.print(f"- {task_id}")
            console.print("Failed Tasks:")
            if run.failed_task_ids:
                for task_id in run.failed_task_ids:
                    console.print(f"- {task_id}")
            else:
                console.print("-")
            console.print("\nTask Summary:")
            for task in tasks:
                console.print(f"- {task.id} {task.status} {escape(redact_text(task.title))}")
    except CodingAgentError as exc:
        console.print(f"[red]Error:[/red] {escape(redact_text(exc))}")
        raise typer.Exit(code=1) from exc
