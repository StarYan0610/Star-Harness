from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.models.run import Run
from app.models.task import Task
from app.utils.redaction import redact_data, redact_text
from app.utils.text import truncate_text


class ReportService:
    def generate(self, run: Run, tasks: list[Task], run_dir: Path) -> Path:
        lines = [
            f"# Coding Agent Report",
            "",
            f"- Run ID: {run.id}",
            f"- Status: {run.status}",
            f"- Command: {run.command}",
            f"- Path: {run.path}",
            f"- Requirement: {self._summary(run.requirement)}",
            f"- Error: {self._summary(run.error_message)}",
            "",
            "## Safety Notice",
            "",
            "Verification commands execute in the target project with the current user's local permissions "
            "through shell compatibility mode. Review commands before running them; this tool never pushes automatically.",
            "",
        ]
        lines.extend(self._plan_section(run_dir))
        lines.extend(self._git_section(run_dir))
        lines.extend(self._audit_section(run_dir))
        lines.extend(["## Tasks", ""])
        for task in tasks:
            attempts = self._load_attempts(run_dir, task.id)
            lines.extend(
                [
                    f"### {task.order_index}. {redact_text(task.title)}",
                    "",
                    f"- Task ID: {task.id}",
                    f"- Status: {task.status}",
                    f"- Review: {task.review_status or ''}",
                    f"- Review Summary: {self._summary(task.review_summary)}",
                    f"- Review Findings: {self._summary(json.dumps(redact_data(task.review_findings or []), ensure_ascii=False))}",
                    f"- Summary: {self._summary(task.summary)}",
                    f"- Error: {self._summary(task.error_message)}",
                ]
            )
            if attempts:
                max_attempts = attempts[-1].get("max_attempts", len(attempts))
                lines.append(f"- Attempts: {len(attempts)} / {max_attempts}")
                for attempt in attempts:
                    lines.append(
                        "- Attempt "
                        f"{attempt.get('attempt')}: {attempt.get('outcome')}; "
                        f"executor={attempt.get('executor_success')}; "
                        f"review={attempt.get('review_status')}; "
                        f"reason={self._summary(attempt.get('failure_summary') or attempt.get('review_summary', ''))}"
                    )
            lines.append("")
        report_path = run_dir / "report.md"
        report_path.write_text(redact_text("\n".join(lines)), encoding="utf-8")
        return report_path

    @staticmethod
    def _load_attempts(run_dir: Path, task_id: str) -> list[dict]:
        attempts_path = run_dir / "tasks" / task_id / "attempts.json"
        if not attempts_path.exists():
            return []
        try:
            payload = json.loads(attempts_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        attempts = payload.get("attempts") if isinstance(payload, dict) else None
        return [item for item in attempts if isinstance(item, dict)] if isinstance(attempts, list) else []

    @staticmethod
    def _summary(value: object | None) -> str:
        return truncate_text(redact_text(value), settings.retry_feedback_max_chars)

    def _git_section(self, run_dir: Path) -> list[str]:
        before = self._load_json(run_dir / "git_before.json")
        after = self._load_json(run_dir / "git_after.json")
        commit = self._load_json(run_dir / "git_commit.json")
        if not before and not after:
            return []
        lines = ["## Git Safety", ""]
        lines.extend(self._format_git_snapshot("Before", before))
        lines.extend(self._format_git_snapshot("After", after))
        if commit:
            lines.append(f"- Local Commit: {self._summary(commit.get('message'))}")
            if commit.get("commit_id"):
                lines.append(f"- Commit ID: {commit['commit_id']}")
        lines.append("")
        return lines

    def _plan_section(self, run_dir: Path) -> list[str]:
        plan = self._load_json(run_dir / "plan.json")
        if not plan:
            return []
        raw_tasks = plan.get("tasks")
        task_count = len(raw_tasks) if isinstance(raw_tasks, list) else 0
        lines = ["## Plan", ""]
        lines.extend(
            [
                f"- Strategy: {self._summary(plan.get('strategy_name'))}",
                f"- Source: {self._summary(plan.get('source_type'))}",
                f"- Input Summary: {self._summary(plan.get('source_summary'))}",
                f"- Planned Tasks: {task_count}",
                f"- Truncated: {bool(plan.get('truncated'))}",
            ]
        )
        if plan.get("truncation_reason"):
            lines.append(f"- Truncation Reason: {self._summary(plan.get('truncation_reason'))}")
        lines.append("")
        return lines

    def _audit_section(self, run_dir: Path) -> list[str]:
        plan = self._load_json(run_dir / "plan.json")
        if plan.get("source_type") != "audit-report":
            return []
        total = int(plan.get("audit_total_items") or 0)
        unprocessed = plan.get("unprocessed_audit_items") or []
        if not isinstance(unprocessed, list):
            unprocessed = []
        processed = max(0, total - len(unprocessed))
        range_text = "; ".join(
            f"[{item.get('severity', 'medium')}] {item.get('title', '')}"
            for item in unprocessed
            if isinstance(item, dict)
        )
        lines = ["## Audit Coverage", ""]
        lines.append(f"- Processed Audit Items: {processed} / {total}")
        lines.append(f"- Unprocessed Audit Items: {len(unprocessed)}")
        if unprocessed:
            lines.append(f"- Unprocessed Range: {self._summary(range_text)}")
        lines.append("")
        return lines

    def _format_git_snapshot(self, label: str, snapshot: dict) -> list[str]:
        if not snapshot:
            return []
        if not snapshot.get("is_repository"):
            return [f"- {label}: not a Git repository"]
        files = snapshot.get("affected_files") or []
        files_text = ", ".join(str(item) for item in files) or "none"
        if snapshot.get("files_truncated"):
            files_text += ", ...[truncated]"
        return [
            f"- {label} Branch: {snapshot.get('branch') or 'detached'}",
            f"- {label} Dirty: {snapshot.get('dirty')}",
            f"- {label} Diff Summary: {self._summary(snapshot.get('diff_summary'))}",
            f"- {label} Possible Files: {self._summary(files_text)}",
        ]

    @staticmethod
    def _load_json(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
