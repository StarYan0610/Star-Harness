from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.llm.base import LLMClient, LLMMessage
from app.llm.openai_client import OpenAIChatClient
from app.planners.base import Planner
from app.schemas.plan import Plan
from app.schemas.run import AuditReport
from app.schemas.task import CodingTask
from app.utils.id_generator import generate_uuid


class LLMTaskDraft(BaseModel):
    title: str
    description: str
    scope: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)


class LLMPlanDraft(BaseModel):
    tasks: list[LLMTaskDraft] = Field(default_factory=list)


class LLMPlanner(Planner):
    def __init__(self, client: LLMClient | None = None):
        self.client = client or OpenAIChatClient()

    def plan(
        self,
        *,
        run_id: str,
        command: str,
        path: str,
        requirement: str | None,
        update_mode: str | None,
        audit_report: AuditReport | None,
        strategy_name: str,
        strategy_text: str,
        max_tasks: int,
        project_memory: str = "",
    ) -> Plan:
        source_type = "audit-report" if audit_report else "requirement"
        source_summary = audit_report.summary if audit_report else (requirement or "")
        draft = self._create_draft(
            command=command,
            path=path,
            requirement=requirement,
            update_mode=update_mode,
            audit_report=audit_report,
            strategy_name=strategy_name,
            strategy_text=strategy_text,
            max_tasks=max_tasks,
            project_memory=project_memory,
        )
        if not draft.tasks:
            raise ValidationError("LLM planner returned no tasks")
        truncated = len(draft.tasks) > max_tasks
        tasks = draft.tasks[:max_tasks]
        unprocessed_audit_items = audit_report.items[len(tasks) :] if audit_report else []
        if unprocessed_audit_items:
            truncated = True
        return Plan(
            run_id=run_id,
            strategy_name=strategy_name,
            max_tasks=max_tasks,
            source_type=source_type,
            source_summary=source_summary,
            truncated=truncated,
            truncation_reason=(
                "audit item count exceeded max_tasks"
                if unprocessed_audit_items
                else "task count exceeded max_tasks"
                if truncated
                else None
            ),
            audit_total_items=len(audit_report.items) if audit_report else 0,
            unprocessed_audit_items=unprocessed_audit_items,
            tasks=[
                CodingTask(
                    task_id=generate_uuid(),
                    order_index=index + 1,
                    title=task.title,
                    description=task.description,
                    scope=task.scope or ["."],
                    acceptance_criteria=task.acceptance_criteria,
                    verification_commands=task.verification_commands,
                )
                for index, task in enumerate(tasks)
            ],
        )

    def _create_draft(
        self,
        *,
        command: str,
        path: str,
        requirement: str | None,
        update_mode: str | None,
        audit_report: AuditReport | None,
        strategy_name: str,
        strategy_text: str,
        max_tasks: int,
        project_memory: str,
    ) -> LLMPlanDraft:
        content = self.client.complete_json(
            [
                LLMMessage(role="system", content=self._system_prompt()),
                LLMMessage(
                    role="user",
                    content=self._user_prompt(
                        command=command,
                        path=path,
                        requirement=requirement,
                        update_mode=update_mode,
                        audit_report=audit_report,
                        strategy_name=strategy_name,
                        strategy_text=strategy_text,
                        max_tasks=max_tasks,
                        project_memory=project_memory,
                    ),
                ),
            ]
        )
        return self._parse_response(content)

    def _parse_response(self, content: str) -> LLMPlanDraft:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"LLM planner returned invalid JSON: {exc}") from exc
        if isinstance(payload, list):
            payload = {"tasks": payload}
        if not isinstance(payload, dict):
            raise ValidationError("LLM planner JSON must be an object")
        tasks_payload = payload.get("tasks")
        if not isinstance(tasks_payload, list):
            raise ValidationError("LLM planner JSON must contain a tasks array")
        try:
            return LLMPlanDraft.model_validate({"tasks": [self._normalize_task(item) for item in tasks_payload]})
        except PydanticValidationError as exc:
            raise ValidationError(f"LLM planner JSON schema validation failed: {exc}") from exc

    def _normalize_task(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValidationError("each LLM planner task must be an object")
        return {
            "title": str(item.get("title") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "scope": self._string_list(item.get("scope")),
            "acceptance_criteria": self._string_list(item.get("acceptance_criteria")),
            "verification_commands": self._string_list(item.get("verification_commands")),
        }

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _system_prompt(self) -> str:
        return (
            "你是一个资深 Coding Agent 任务规划器。"
            "你的职责是把用户需求拆成少量、具体、可串行执行、可验收的编码任务。"
            "只输出 JSON，不要输出 Markdown。"
        )

    def _user_prompt(
        self,
        *,
        command: str,
        path: str,
        requirement: str | None,
        update_mode: str | None,
        audit_report: AuditReport | None,
        strategy_name: str,
        strategy_text: str,
        max_tasks: int,
        project_memory: str,
    ) -> str:
        audit_text = ""
        if audit_report:
            audit_text = (
                f"\n审计报告摘要：{audit_report.summary}\n"
                f"结构化审计项：{[item.model_dump() for item in audit_report.items]}\n"
            )
        memory_text = f"\n项目只读约定：\n{project_memory}\n" if project_memory else ""
        return f"""
请为 Coding Agent 生成执行计划。

命令类型：{command}
目标目录：{path}
更新模式：{update_mode or "无"}
需求：{requirement or "无"}
策略名称：{strategy_name}
策略说明：
{strategy_text}
{audit_text}
{memory_text}

约束：
- 最多输出 {max_tasks} 个任务。
- 任务必须串行可执行，前一个任务完成后才能进入后一个任务。
- 每个任务必须具体说明要实现或修改什么，不要写“第一组核心功能”这类空泛描述。
- create 命令的第一个任务应该是项目骨架和最小运行闭环。
- update 命令的第一个任务应该是分析现有项目结构和影响范围。
- 骨架任务最多规划 3 个以内对外接口或命令。
- 每个任务必须包含 title、description、scope、acceptance_criteria、verification_commands。
- scope 是预计修改范围，例如 ["app", "tests", "README.md"]。
- acceptance_criteria 是可验收结果，不少于 2 条。
- verification_commands 是建议执行的本地验证命令；不确定时可以返回 []。
- 不要生成 task_id 和 order_index，这些由系统分配。

输出 JSON 格式：
{{
  "tasks": [
    {{
      "title": "具体任务标题",
      "description": "具体任务说明",
      "scope": ["预计修改路径或目录"],
      "acceptance_criteria": ["验收标准 1", "验收标准 2"],
      "verification_commands": ["验证命令"]
    }}
  ]
}}
""".strip()
