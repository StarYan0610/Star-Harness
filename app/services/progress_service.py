from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from app.schemas.progress import ProgressEvent
from app.utils.id_generator import generate_uuid
from app.utils.jsonl import append_jsonl
from app.utils.redaction import redact_data, redact_text


class ProgressService:
    def __init__(self, run_id: str, run_dir: Path, output: str = "human"):
        self.run_id = run_id
        self.run_dir = run_dir
        self.output = output
        self.console = Console()

    @property
    def events_path(self) -> Path:
        return self.run_dir / "events.jsonl"

    def emit(self, event_type: str, message: str, *, task_id: str | None = None, payload: dict | None = None) -> ProgressEvent:
        event = ProgressEvent(
            id=generate_uuid(),
            run_id=self.run_id,
            task_id=task_id,
            event_type=event_type,
            message=redact_text(message),
            payload=redact_data(payload or {}),
        )
        data = event.model_dump(mode="json")
        append_jsonl(self.events_path, data)
        if self.output == "jsonl":
            # 直接打印，避免长行被折行，保证机器可解析
            print(json.dumps(data, ensure_ascii=False), flush=True)
        else:
            prefix = task_id or self.run_id
            suffix = f" {event.message}" if event.message else ""
            # 输出为普通文本，防止 [] 被解析为 rich 标记，避免自动换行
            self.console.print(
                f"[{prefix}] {event_type}{suffix}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        return event
