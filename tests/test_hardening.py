import json
import stat
import time

from app.core.paths import ensure_agent_dir
from app.executors.codex import CodexExecutor
from app.planners.strategy_loader import StrategyLoader
from app.schemas.task import CodingTask, ExecutionContext
from app.services.progress_service import ProgressService
from app.services.run_service import RunService


def _coding_task() -> CodingTask:
    return CodingTask(
        task_id="8b0f4c0e-6f6a-4a58-9a3f-0f0f4c0e6f6a",
        order_index=1,
        title="任务",
        description="说明",
    )


def test_progress_emit_survives_rich_markup_hostile_content(tmp_path, capsys):
    progress = ProgressService("run", tmp_path, output="human")

    progress.emit("EXECUTOR_OUTPUT", "diff: path a[/b] and [red]text[/red] and list[Todo]")

    captured = capsys.readouterr().out
    assert "a[/b]" in captured
    assert "[red]text[/red]" in captured


def test_progress_jsonl_output_is_single_physical_line(tmp_path, capsys):
    progress = ProgressService("run", tmp_path, output="jsonl")

    progress.emit("EXECUTOR_OUTPUT", "x" * 500)

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["message"] == "x" * 500


def test_codex_executor_kills_run_after_timeout(tmp_path):
    script = tmp_path / "fake-codex"
    script.write_text("#!/bin/sh\necho started\nsleep 30\necho finished\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    executor = CodexExecutor(command=str(script), timeout_seconds=0.5)
    workdir = tmp_path / "project"
    workdir.mkdir()

    started = time.monotonic()
    result = executor.execute(
        _coding_task(),
        ExecutionContext(run_id="run", path=str(workdir), task_dir=str(tmp_path / "attempt")),
    )
    elapsed = time.monotonic() - started

    assert elapsed < 10
    assert result.success is False
    assert "timed out" in result.summary
    log_text = (tmp_path / "attempt" / "executor.log").read_text(encoding="utf-8")
    assert "timed out" in log_text


def test_strategy_loader_resolves_bundled_strategies_from_any_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    text = StrategyLoader().load("skeleton-first")

    assert text.strip()


def test_create_bootstrap_ignores_previous_harness_metadata(tmp_path):
    target = tmp_path / "project"
    (target / ".coding-agent").mkdir(parents=True)
    (target / ".git").mkdir()

    resolved, was_nonempty = RunService._bootstrap_create_target(str(target))

    assert resolved == target
    assert was_nonempty is False


def test_create_bootstrap_still_rejects_project_content(tmp_path):
    target = tmp_path / "project"
    target.mkdir()
    (target / "main.py").write_text("print()\n", encoding="utf-8")

    _, was_nonempty = RunService._bootstrap_create_target(str(target))

    assert was_nonempty is True


def test_ensure_agent_dir_writes_self_gitignore(tmp_path):
    directory = ensure_agent_dir(tmp_path)

    assert directory.is_dir()
    assert (directory / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_ensure_agent_dir_preserves_existing_gitignore(tmp_path):
    directory = tmp_path / ".coding-agent"
    directory.mkdir()
    (directory / ".gitignore").write_text("custom\n", encoding="utf-8")

    ensure_agent_dir(tmp_path)

    assert (directory / ".gitignore").read_text(encoding="utf-8") == "custom\n"
