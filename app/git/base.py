from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.git import GitCommitResult, GitSnapshot


class GitInspector(ABC):
    # 检查 Git 仓库
    @abstractmethod
    def inspect(self, target: Path) -> GitSnapshot:
        raise NotImplementedError

    # 提交 Git 仓库
    @abstractmethod
    def commit(self, target: Path, message: str) -> GitCommitResult:
        raise NotImplementedError
