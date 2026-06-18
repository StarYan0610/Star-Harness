from __future__ import annotations

from pathlib import Path


# 策略与工具一起发布，因此以包路径为准，而不是工作目录
_BUNDLED_STRATEGIES_DIR = Path(__file__).resolve().parents[2] / "strategies"


class StrategyLoader:
    def __init__(self, strategies_dir: Path | None = None):
        self.strategies_dir = strategies_dir or _BUNDLED_STRATEGIES_DIR

    def load(self, strategy_name: str) -> str:
        path = self.strategies_dir / f"{strategy_name}.md"
        if not path.exists():
            raise FileNotFoundError(f"strategy not found: {strategy_name}")
        return path.read_text(encoding="utf-8")
