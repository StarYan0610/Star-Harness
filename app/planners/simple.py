from __future__ import annotations

import re

from app.planners.base import Planner
from app.schemas.plan import Plan
from app.schemas.run import AuditReport
from app.schemas.task import CodingTask
from app.utils.id_generator import generate_uuid


class SimplePlanner(Planner):
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
        planned = self._build_tasks(command, requirement, audit_report)
        truncated = len(planned) > max_tasks
        tasks = planned[:max_tasks]
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
                CodingTask(task_id=generate_uuid(), order_index=i + 1, **task)
                for i, task in enumerate(tasks)
            ],
        )

    def _build_tasks(self, command: str, requirement: str | None, audit_report: AuditReport | None) -> list[dict]:
        if audit_report:
            items = audit_report.items
            return [
                {
                    "title": f"[{item.severity}] 修复审计问题：{item.title}",
                    "description": (
                        f"根据审计报告处理问题：{item.description}\n"
                        f"严重级别：{item.severity}\n补充约束：{requirement or '无'}"
                    ),
                    "scope": ["audit-report"],
                    "acceptance_criteria": ["问题已被定位", "实现最小范围修复", "记录验证结果"],
                    "verification_commands": [],
                }
                for item in items
            ]
        if command == "create":
            return self._build_create_tasks(requirement)
        return [
            {
                "title": "分析目标项目结构和影响范围",
                "description": requirement or "分析现有项目结构，定位修改点。",
                "scope": ["."],
                "acceptance_criteria": ["定位相关文件", "确认修改范围"],
                "verification_commands": [],
            },
            {
                "title": "按需求完成最小代码修改",
                "description": requirement or "完成用户要求的最小安全修改。",
                "scope": ["."],
                "acceptance_criteria": ["实现需求", "避免无关重构"],
                "verification_commands": [],
            },
            {
                "title": "执行聚焦验证并整理结果",
                "description": "运行相关验证，整理结果和风险。",
                "scope": ["tests", "."],
                "acceptance_criteria": ["验证通过或记录失败原因", "生成任务摘要"],
                "verification_commands": ["python3 -m pytest"],
            },
        ]

    def _build_create_tasks(self, requirement: str | None) -> list[dict]:
        requirement_text = requirement or "创建项目骨架、配置、目录结构和最小可运行入口。"
        stack_items = self._detect_stack_items(requirement_text)
        features = self._extract_feature_items(requirement_text)
        tasks: list[dict] = [
            {
                "title": "搭建项目骨架和最小运行闭环",
                "description": self._skeleton_description(requirement_text, stack_items),
                "scope": ["."],
                "acceptance_criteria": [
                    "项目目录结构创建完成",
                    "存在基础配置、依赖声明和最小可运行入口",
                    *[f"技术栈包含：{item}" for item in stack_items],
                    "骨架阶段对外接口或命令数量不超过 3 个",
                ],
                "verification_commands": self._verification_commands(requirement_text),
            }
        ]
        tasks.extend(self._feature_task(feature) for feature in features)
        tasks.append(
            {
                "title": "执行聚焦验证并整理结果",
                "description": f"围绕需求“{requirement_text}”运行可用验证命令，修复明显问题，并在 README 或报告中记录使用方式和剩余风险。",
                "scope": ["tests", "README.md", "."],
                "acceptance_criteria": [
                    "验证命令被执行或说明不可执行原因",
                    "README 记录启动方式、验证方式和已实现功能",
                    "报告记录剩余风险",
                ],
                "verification_commands": self._verification_commands(requirement_text),
            }
        )
        return tasks

    def _detect_stack_items(self, requirement: str) -> list[str]:
        known_items = ["FastAPI", "Django", "Flask", "React", "Vue", "Next.js", "pytest"]
        lowered = requirement.lower()
        found: list[str] = []
        for item in known_items:
            if item.lower() in lowered:
                found.append(item)
        return found

    def _extract_feature_items(self, requirement: str) -> list[str]:
        normalized = requirement.strip().strip("。")
        match = re.search(r"(?:包含|包括|实现|增加|新增|支持|提供)(.+)", normalized)
        feature_text = match.group(1) if match else normalized
        feature_text = re.sub(r"^一个?", "", feature_text)
        parts = [
            item.strip(" ：:，,。. ")
            for item in re.split(r"\s*(?:、|，|,|和|以及|并且|；|;)\s*", feature_text)
        ]
        ignored = {
            "",
            "项目",
            "一个项目",
            "基础项目",
            "创建项目",
            "搭建项目",
            "项目骨架",
            "基础配置",
        }
        features: list[str] = []
        for part in parts:
            part = re.sub(r"^(创建|搭建|开发|实现|增加|新增|支持|提供)一个?", "", part).strip()
            part = re.sub(r"项目$", "", part).strip()
            if part in ignored or len(part) < 2:
                continue
            if self._looks_like_stack_only(part):
                continue
            if part not in features:
                features.append(part)
        return features[:5]

    def _looks_like_stack_only(self, item: str) -> bool:
        return item.lower() in {"fastapi", "django", "flask", "react", "vue", "next.js", "python"}

    def _feature_task(self, feature: str) -> dict:
        return {
            "title": f"实现核心功能：{feature}",
            "description": f"围绕“{feature}”完成最小可用实现，必要时补充对外接口、配置、文档或测试，避免无关扩展。",
            "scope": self._scope_for_feature(feature),
            "acceptance_criteria": [
                f"“{feature}”具备最小可用实现",
                f"可以通过代码、接口、文档或测试验证“{feature}”",
                "修改范围聚焦，不引入无关模块",
            ],
            "verification_commands": self._verification_commands(feature),
        }

    def _scope_for_feature(self, feature: str) -> list[str]:
        lowered = feature.lower()
        if "readme" in lowered or "文档" in feature:
            return ["README.md"]
        if "接口" in feature or "api" in lowered or "健康检查" in feature:
            return ["app", "tests"]
        return ["app", "tests", "README.md"]

    def _verification_commands(self, text: str) -> list[str]:
        # macOS ships python3 without a `python` alias, so `python -m pytest` would fail
        # with exit 127 even when the generated project is healthy.
        return ["python3 -m pytest"]

    def _skeleton_description(self, requirement: str, stack_items: list[str]) -> str:
        stack_text = "、".join(stack_items) if stack_items else "需求中指定的技术栈"
        return (
            f"根据需求“{requirement}”创建项目骨架、基础配置、目录结构和最小可运行入口。"
            f"骨架需体现{stack_text}，并为后续核心功能任务预留清晰扩展位置。"
        )
