from __future__ import annotations

from pathlib import Path

from app.core.exceptions import BootstrapError

# 确保路径是绝对路径
def ensure_absolute_path(path: str) -> Path:
    """Expand the user directory and reject relative project paths."""
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise BootstrapError("path must be an absolute path")
    return target

# 返回 .coding-agent 目录路径
def agent_dir(target_path: Path) -> Path:
    """Return the runtime metadata directory within a project."""
    return target_path / ".coding-agent"

# 确保代理目录存在
def ensure_agent_dir(target_path: Path) -> Path:
    """Create .coding-agent and keep it out of the user's Git status via a self-ignore."""
    directory = agent_dir(target_path)
    directory.mkdir(parents=True, exist_ok=True)
    gitignore = directory / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")
    return directory


def runs_dir(target_path: Path) -> Path:
    """Return the parent directory for persisted run artifacts."""
    return agent_dir(target_path) / "runs"


def run_dir(target_path: Path, run_id: str) -> Path:
    return runs_dir(target_path) / run_id


def db_path(target_path: Path) -> Path:
    return agent_dir(target_path) / "coding-agent.db"
