from __future__ import annotations

import subprocess
from pathlib import Path

from app.git.base import GitInspector
from app.schemas.git import GitCommitResult, GitSnapshot

# 命令行 Git 检查器
class CommandGitInspector(GitInspector):
    """Read local Git state and optionally create a local commit; never pushes."""

    _MAX_AFFECTED_FILES = 100

    # 检查 Git 仓库
    def inspect(self, target: Path) -> GitSnapshot:
        inside_work_tree = self._run(target, "rev-parse", "--is-inside-work-tree")
        if inside_work_tree is None or inside_work_tree.returncode != 0:
            return GitSnapshot(is_repository=False)

        branch_result = self._run(target, "branch", "--show-current")
        branch = branch_result.stdout.strip() if branch_result and branch_result.returncode == 0 else ""
        if not branch:
            head_result = self._run(target, "rev-parse", "--short", "HEAD")
            if head_result and head_result.returncode == 0:
                branch = f"detached@{head_result.stdout.strip()}"

        status_result = self._run(target, "status", "--porcelain=v1", "--untracked-files=all")
        status_lines = status_result.stdout.splitlines() if status_result and status_result.returncode == 0 else []
        affected_files = self._affected_files(status_lines)
        dirty = bool(affected_files)
        diff_summary = self._diff_summary(target, dirty)
        return GitSnapshot(
            is_repository=True,
            branch=branch or None,
            dirty=dirty,
            diff_summary=diff_summary,
            affected_files=affected_files[: self._MAX_AFFECTED_FILES],
            files_truncated=len(affected_files) > self._MAX_AFFECTED_FILES,
        )

    # 提交 Git 仓库
    def commit(self, target: Path, message: str) -> GitCommitResult:
        snapshot = self.inspect(target)
        if not snapshot.is_repository:
            return GitCommitResult(created=False, message="local commit skipped: target is not a Git repository")

        add_result = self._run(target, "add", "-A", "--", ".", ":(exclude).coding-agent")
        if add_result is None or add_result.returncode != 0:
            return GitCommitResult(created=False, message=self._failure_message("git add", add_result))
        cached = self._run(target, "diff", "--cached", "--quiet")
        if cached is None:
            return GitCommitResult(created=False, message="git diff --cached could not be started")
        if cached.returncode == 0:
            return GitCommitResult(created=False, message="local commit skipped: no project changes to commit")
        if cached.returncode != 1:
            return GitCommitResult(created=False, message=self._failure_message("git diff --cached", cached))

        commit_result = self._run(target, "commit", "-m", message)
        if commit_result is None or commit_result.returncode != 0:
            return GitCommitResult(created=False, message=self._failure_message("git commit", commit_result))
        head_result = self._run(target, "rev-parse", "--short", "HEAD")
        commit_id = head_result.stdout.strip() if head_result and head_result.returncode == 0 else None
        return GitCommitResult(created=True, commit_id=commit_id, message="local commit created")

    # 获取差异摘要
    def _diff_summary(self, target: Path, dirty: bool) -> str:
        if not dirty:
            return "clean working tree"
        summaries: list[str] = []
        for args in (
            ("diff", "--stat", "--", ".", ":(exclude).coding-agent"),
            ("diff", "--cached", "--stat", "--", ".", ":(exclude).coding-agent"),
        ):
            result = self._run(target, *args)
            if result and result.returncode == 0 and result.stdout.strip():
                summaries.append(result.stdout.strip())
        return "\n".join(summaries) or "untracked or metadata-only project changes"

    # 获取受影响的文件
    @staticmethod
    def _affected_files(status_lines: list[str]) -> list[str]:
        files: list[str] = []
        for line in status_lines:
            path = line[3:].strip()
            if path.startswith(".coding-agent/") or path == ".coding-agent":
                continue
            if path:
                files.append(path)
        return files

    # 获取失败消息
    @staticmethod
    def _failure_message(command: str, result: subprocess.CompletedProcess[str] | None) -> str:
        detail = "could not be started" if result is None else (result.stderr.strip() or result.stdout.strip())
        return f"{command} failed: {detail}"

    # 运行命令
    @staticmethod
    def _run(target: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=target,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
