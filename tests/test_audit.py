import json

from app.executors.base import CodingExecutor
from app.planners.simple import SimplePlanner
from app.reviewers.basic import BasicReviewer
from app.schemas.task import ExecutionResult
from app.services.planning_service import PlanningService
from app.services.run_service import RunService
from app.utils.audit import load_audit_report


class NoopExecutor(CodingExecutor):
    def execute(self, task, context, on_output=None) -> ExecutionResult:
        return ExecutionResult(success=True, summary="audit item handled", exit_code=0)


def test_audit_parser_builds_and_prioritizes_structured_json_items(tmp_path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "issues": [
                    {"severity": "low", "title": "Copy typo", "description": "Fix UI wording."},
                    {"severity": "critical", "title": "SQL injection", "description": "Bind query parameters."},
                    {"severity": "medium", "title": "Missing test", "description": "Add regression coverage."},
                ]
            }
        ),
        encoding="utf-8",
    )

    audit = load_audit_report(str(audit_path))
    plan = SimplePlanner().plan(
        run_id="run",
        command="update",
        path="/tmp/project",
        requirement=None,
        update_mode="audit-report",
        audit_report=audit,
        strategy_name="skeleton-first",
        strategy_text="strategy",
        max_tasks=1,
    )

    assert [(item.severity, item.title) for item in audit.items] == [
        ("high", "SQL injection"),
        ("medium", "Missing test"),
        ("low", "Copy typo"),
    ]
    assert audit.items[0].raw_severity == "critical"
    assert plan.tasks[0].title.startswith("[high]")
    assert plan.truncated is True
    assert plan.audit_total_items == 3
    assert [item.title for item in plan.unprocessed_audit_items] == ["Missing test", "Copy typo"]


def test_audit_parser_supports_markdown_items(tmp_path):
    audit_path = tmp_path / "audit.md"
    audit_path.write_text(
        "# Audit\n\n- LOW: Documentation wording: Clarify the setup steps.\n- HIGH: Injection risk: Bind inputs.\n",
        encoding="utf-8",
    )

    audit = load_audit_report(str(audit_path))

    assert [(item.severity, item.title, item.description) for item in audit.items] == [
        ("high", "Injection risk", "Bind inputs."),
        ("low", "Documentation wording", "Clarify the setup steps."),
    ]


def test_audit_parser_accepts_bracketed_severity_in_headings_and_bullets(tmp_path):
    audit_path = tmp_path / "audit.md"
    audit_path.write_text(
        "## [HIGH] Injection risk\nBind inputs.\n\n- [LOW] Copy typo: Fix UI wording.\n",
        encoding="utf-8",
    )

    audit = load_audit_report(str(audit_path))

    assert [(item.severity, item.title) for item in audit.items] == [
        ("high", "Injection risk"),
        ("low", "Copy typo"),
    ]


def test_audit_parser_accepts_a_severity_heading_without_body(tmp_path):
    audit_path = tmp_path / "audit.md"
    audit_path.write_text("# Audit Report\n\n## HIGH: SQL injection\n", encoding="utf-8")

    audit = load_audit_report(str(audit_path))

    assert [(item.severity, item.title, item.description) for item in audit.items] == [
        ("high", "SQL injection", "SQL injection"),
    ]


def test_audit_run_reports_unprocessed_item_count_and_range(tmp_path):
    target = tmp_path / "project"
    target.mkdir()
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "findings": [
                    {"severity": "high", "title": "SQL injection", "description": "Bind inputs."},
                    {"severity": "medium", "title": "Missing test", "description": "Add coverage."},
                    {"severity": "low", "title": "Copy typo", "description": "Fix wording."},
                ]
            }
        ),
        encoding="utf-8",
    )
    service = RunService(executor=NoopExecutor(), reviewer=BasicReviewer())
    service.planning_service = PlanningService(planner=SimplePlanner())

    run = service.update(
        path=str(target),
        update_mode="audit-report",
        requirement=None,
        audit_report_path=str(audit_path),
        strategy="skeleton-first",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    run_dir = target / ".coding-agent" / "runs" / run.id
    plan = json.loads(run_dir.joinpath("plan.json").read_text(encoding="utf-8"))
    report = run_dir.joinpath("report.md").read_text(encoding="utf-8")

    assert run.status == "SUCCESS"
    assert plan["audit_total_items"] == 3
    assert len(plan["unprocessed_audit_items"]) == 2
    assert "## Plan" in report
    assert "Strategy: skeleton-first" in report
    assert "## Audit Coverage" in report
    assert "Processed Audit Items: 1 / 3" in report
    assert "Unprocessed Audit Items: 2" in report
    assert "[medium] Missing test" in report
    assert "[low] Copy typo" in report


def test_empty_audit_report_is_a_project_validation_failure(tmp_path):
    target = tmp_path / "project"
    target.mkdir()
    audit_path = tmp_path / "audit.md"
    audit_path.write_text("# Audit Report\n", encoding="utf-8")
    service = RunService(executor=NoopExecutor(), reviewer=BasicReviewer())

    run = service.update(
        path=str(target),
        update_mode="audit-report",
        requirement=None,
        audit_report_path=str(audit_path),
        strategy="skeleton-first",
        max_tasks=1,
        output="jsonl",
        executor="fake",
    )

    report = target.joinpath(".coding-agent", "runs", run.id, "report.md").read_text(encoding="utf-8")
    assert run.status == "FAILED"
    assert "audit-report contains no valid audit items" in report
