import json
from pathlib import Path

from app.domain.enums import ReviewStatus
from app.executors.base import CodingExecutor
from app.planners.simple import SimplePlanner
from app.reviewers.base import Reviewer
from app.schemas.task import CodingTask, ExecutionResult, ReviewResult
from app.services.planning_service import PlanningService
from app.services.progress_service import ProgressService
from app.services.run_service import RunService
from app.utils.redaction import REDACTED, redact_data, redact_text


SECRET = "sk-top-secret-123456789"


class SecretExecutor(CodingExecutor):
    def __init__(self):
        self.contexts = []

    def execute(self, task, context, on_output=None) -> ExecutionResult:
        self.contexts.append(context)
        log_path = Path(context.task_dir) / "executor.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"OPENAI_API_KEY={SECRET}\nAuthorization: Bearer {SECRET}\n", encoding="utf-8")
        return ExecutionResult(
            success=False,
            summary=f"executor failed with OPENAI_API_KEY={SECRET}",
            error_message=f"token={SECRET}",
            exit_code=1,
            log_path=str(log_path),
        )


class SecretReviewer(Reviewer):
    def review(self, task, result, context) -> ReviewResult:
        return ReviewResult(
            status=ReviewStatus.FAILED.value,
            summary=f"review failed: Authorization: Bearer {SECRET}",
            findings=[{"api_key": SECRET, "detail": f"password={SECRET}"}],
        )


def test_redaction_handles_text_and_nested_payloads():
    opaque_bearer = "opaque-session-value"
    text = (
        f"OPENAI_API_KEY={SECRET}; Authorization: Bearer {opaque_bearer}; "
        "GITHUB_TOKEN=not-a-known-prefix; AWS_SECRET_ACCESS_KEY=aws-secret-value; "
        "github_pat_abcdefgh123456"
    )
    payload = {"api_key": SECRET, "token": opaque_bearer, "nested": [f"token={SECRET}"]}

    assert SECRET not in redact_text(text)
    assert opaque_bearer not in redact_text(text)
    assert "not-a-known-prefix" not in redact_text(text)
    assert "aws-secret-value" not in redact_text(text)
    assert REDACTED in redact_text(text)
    assert redact_data(payload) == {
        "api_key": REDACTED,
        "token": REDACTED,
        "nested": ["token=[REDACTED]"],
    }


def test_progress_service_redacts_terminal_and_event_body(tmp_path, capsys):
    progress = ProgressService("run", tmp_path, output="jsonl")
    progress.emit("TEST", f"OPENAI_API_KEY={SECRET}", payload={"token": SECRET})

    event_text = tmp_path.joinpath("events.jsonl").read_text(encoding="utf-8")
    terminal_text = capsys.readouterr().out

    assert SECRET not in event_text
    assert SECRET not in terminal_text
    assert REDACTED in event_text


def test_progress_service_redacts_human_terminal_output(tmp_path, capsys):
    progress = ProgressService("run", tmp_path, output="human")
    progress.emit("TEST", f"OPENAI_API_KEY={SECRET}")

    terminal_text = capsys.readouterr().out

    assert SECRET not in terminal_text
    assert REDACTED in terminal_text


def test_run_artifacts_report_events_and_retry_feedback_redact_secrets(tmp_path):
    target = tmp_path / "project"
    executor = SecretExecutor()
    service = RunService(executor=executor, reviewer=SecretReviewer())
    service.planning_service = PlanningService(planner=SimplePlanner())

    run = service.create(
        path=str(target),
        requirement=f"implement feature with OPENAI_API_KEY={SECRET}",
        strategy="skeleton-first",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    run_dir = target / ".coding-agent" / "runs" / run.id
    report = run_dir.joinpath("report.md").read_text(encoding="utf-8")
    events = run_dir.joinpath("events.jsonl").read_text(encoding="utf-8")
    attempts = run_dir.joinpath("tasks").glob("*/attempts.json")
    attempt_text = next(attempts).read_text(encoding="utf-8")
    feedback = executor.contexts[1].retry_feedback

    assert run.status == "FAILED"
    assert feedback is not None
    assert SECRET not in feedback.model_dump_json()
    assert SECRET not in report
    assert SECRET not in events
    assert SECRET not in attempt_text
    assert REDACTED in report
    assert REDACTED in events or "[REDACTED]" in feedback.model_dump_json()
    assert SECRET not in target.joinpath(".coding-agent", "runs", run.id, "input.md").read_text(encoding="utf-8")

    parsed_events = [json.loads(line) for line in events.splitlines()]
    assert all(SECRET not in json.dumps(event, ensure_ascii=False) for event in parsed_events)
