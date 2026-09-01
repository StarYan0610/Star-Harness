from __future__ import annotations

import typer

from app.cli.commands.create import app as create_app
from app.cli.commands.report import app as report_app
from app.cli.commands.status import app as status_app
from app.cli.commands.update import app as update_app

# 引入子命令模块，分别对应 create、report、status 和 update 功能
app = typer.Typer(
    help=(
        "Local coding orchestration agent. Verification commands run in the target project "
        "through shell compatibility mode with the current user's local permissions; use only trusted inputs."
    )
)
app.add_typer(create_app)
app.add_typer(update_app)
app.add_typer(status_app)
app.add_typer(report_app)


if __name__ == "__main__":
    app()
