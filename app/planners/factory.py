from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.planners.base import Planner
from app.planners.llm import LLMPlanner
from app.planners.simple import SimplePlanner


class PlannerFactory:
    @staticmethod
    def create(name: str | None = None) -> Planner:
        planner_name = (name or settings.default_planner).strip().lower()
        if planner_name == "simple":
            return SimplePlanner()
        if planner_name in {"openai", "llm"}:
            if not (settings.openai_api_key or "").strip():
                return SimplePlanner()
            if settings.llm_provider.strip().lower() != "openai":
                raise ValidationError(f"unsupported LLM_PROVIDER: {settings.llm_provider}")
            return LLMPlanner()
        raise ValidationError(f"unsupported planner: {planner_name}")
