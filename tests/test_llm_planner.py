import json

import pytest

from app.core.exceptions import ValidationError
from app.llm.base import LLMClient, LLMMessage
from app.planners.llm import LLMPlanner


class FakeLLMClient(LLMClient):
    def __init__(self, payload):
        self.payload = payload
        self.messages: list[LLMMessage] = []

    def complete_json(self, messages: list[LLMMessage]) -> str:
        self.messages = messages
        return json.dumps(self.payload, ensure_ascii=False)


def test_llm_planner_uses_model_tasks_and_assigns_ids():
    planner = LLMPlanner(
        client=FakeLLMClient(
            {
                "tasks": [
                    {
                        "title": "搭建 FastAPI 骨架",
                        "description": "创建基础项目结构和最小启动入口",
                        "scope": ["."],
                        "acceptance_criteria": ["项目可启动", "存在基础配置"],
                        "verification_commands": ["python -m pytest"],
                    },
                    {
                        "title": "实现健康检查接口",
                        "description": "增加 /health 接口和测试",
                        "scope": ["app", "tests"],
                        "acceptance_criteria": ["接口返回正常状态", "测试覆盖接口"],
                        "verification_commands": ["python -m pytest"],
                    },
                ]
            }
        )
    )

    plan = planner.plan(
        run_id="550e8400-e29b-41d4-a716-446655440000",
        command="create",
        path="/tmp/demo",
        requirement="创建一个 FastAPI 项目，包含健康检查接口和 README",
        update_mode=None,
        audit_report=None,
        strategy_name="skeleton-first",
        strategy_text="strategy",
        max_tasks=6,
    )

    assert len(plan.tasks) == 2
    assert plan.tasks[0].task_id
    assert plan.tasks[0].order_index == 1
    assert plan.tasks[1].title == "实现健康检查接口"


def test_llm_planner_truncates_model_tasks_to_max_tasks():
    planner = LLMPlanner(
        client=FakeLLMClient(
            {
                "tasks": [
                    {"title": "任务一", "description": "说明一", "acceptance_criteria": ["验收一", "验收二"]},
                    {"title": "任务二", "description": "说明二", "acceptance_criteria": ["验收一", "验收二"]},
                ]
            }
        )
    )

    plan = planner.plan(
        run_id="550e8400-e29b-41d4-a716-446655440000",
        command="create",
        path="/tmp/demo",
        requirement="搭建项目",
        update_mode=None,
        audit_report=None,
        strategy_name="skeleton-first",
        strategy_text="strategy",
        max_tasks=1,
    )

    assert len(plan.tasks) == 1
    assert plan.truncated is True


def test_llm_planner_rejects_invalid_json_shape():
    planner = LLMPlanner(client=FakeLLMClient({"items": []}))

    with pytest.raises(ValidationError):
        planner.plan(
            run_id="550e8400-e29b-41d4-a716-446655440000",
            command="create",
            path="/tmp/demo",
            requirement="搭建项目",
            update_mode=None,
            audit_report=None,
            strategy_name="skeleton-first",
            strategy_text="strategy",
            max_tasks=1,
        )

