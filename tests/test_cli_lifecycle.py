import re

from typer.testing import CliRunner

from app.cli.main import app


runner = CliRunner()


def test_usage_limits_exit_two_without_creating_a_run(tmp_path):
    target = tmp_path / "project"

    max_tasks = runner.invoke(
        app,
        ["create", "--path", str(target), "--requirement", "test", "--max-tasks", "9"],
    )
    max_attempts = runner.invoke(
        app,
        ["create", "--path", str(target), "--requirement", "test", "--max-attempts", "5"],
    )

    assert max_tasks.exit_code == 2
    assert max_attempts.exit_code == 2
    assert not target.exists()


def test_missing_required_option_is_a_usage_error(tmp_path):
    target = tmp_path / "project"

    result = runner.invoke(app, ["create", "--path", str(target)])

    assert result.exit_code == 2
    assert not target.exists()


def test_bootstrap_failure_exits_one_without_agent_artifacts(tmp_path):
    missing_target = tmp_path / "missing-parent" / "project"
    result = runner.invoke(
        app,
        ["create", "--path", str(missing_target), "--requirement", "test"],
    )

    assert result.exit_code == 1
    assert not missing_target.exists()
    assert not tmp_path.joinpath("missing-parent", ".coding-agent").exists()


def test_non_absolute_and_missing_update_paths_are_bootstrap_failures(tmp_path):
    relative = runner.invoke(
        app,
        ["create", "--path", "relative-project", "--requirement", "test"],
    )
    missing_target = tmp_path / "missing-update"
    update = runner.invoke(
        app,
        [
            "update",
            "--path",
            str(missing_target),
            "--update-mode",
            "requirement",
            "--requirement",
            "test",
        ],
    )

    assert relative.exit_code == 1
    assert update.exit_code == 1
    assert not missing_target.exists()


def test_project_validation_failure_creates_failed_run_and_readable_report(tmp_path):
    target = tmp_path / "project"
    target.mkdir()
    target.joinpath("existing.txt").write_text("keep\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["create", "--path", str(target), "--requirement", "test"],
    )

    run_id_match = re.search(r"Run ID: ([0-9a-f-]+)", result.output)
    assert result.exit_code == 1
    assert run_id_match is not None
    run_id = run_id_match.group(1)
    assert target.joinpath(".coding-agent", "runs", run_id, "report.md").exists()

    status_result = runner.invoke(app, ["status", "--path", str(target), "--run-id", run_id])
    report_result = runner.invoke(app, ["report", "--path", str(target), "--run-id", run_id])

    assert status_result.exit_code == 0
    assert "Status: FAILED" in status_result.output
    assert report_result.exit_code == 0
    assert "create target directory must be empty" in report_result.output


def test_status_on_project_without_database_is_read_only(tmp_path):
    target = tmp_path / "project"
    target.mkdir()

    result = runner.invoke(app, ["status", "--path", str(target), "--run-id", "missing"])

    assert result.exit_code == 1
    assert not target.joinpath(".coding-agent").exists()


def test_cli_help_discloses_local_verification_command_permissions():
    result = runner.invoke(app, ["--help"])
    help_text = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "current user's local permissions" in help_text
    assert "shell compatibility mode" in help_text
