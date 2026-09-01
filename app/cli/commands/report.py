from __future__ import annotations

import typer
from rich.console import Console
from rich.markup import escape

from app.core.paths import ensure_absolute_path, run_dir
from app.core.exceptions import CodingAgentError
from app.utils.redaction import redact_text

app = typer.Typer()
console = Console()

# 生成报告
@app.command("report")
def report(path: str = typer.Option(..., "--path"), run_id: str = typer.Option(..., "--run-id")) -> None:
    try:
        # 确保路径存在且为目录
        target = ensure_absolute_path(path)
        if not target.exists() or not target.is_dir():
            raise CodingAgentError("project directory must exist")
        # 获取报告路径
        report_path = run_dir(target, run_id) / "report.md"
        if not report_path.exists():
            console.print(f"[red]report not found:[/red] {report_path}")
            raise typer.Exit(code=1)
        # 打印报告
        console.print(
            redact_text(report_path.read_text(encoding="utf-8")),
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
    except CodingAgentError as exc:
        console.print(f"[red]Error:[/red] {escape(redact_text(exc))}")
        raise typer.Exit(code=1) from exc
