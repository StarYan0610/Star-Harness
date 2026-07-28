import pytest

from app.core.exceptions import ValidationError
from app.planners.factory import PlannerFactory
from app.planners.llm import LLMPlanner
from app.planners.simple import SimplePlanner


def test_planner_factory_creates_simple_planner():
    planner = PlannerFactory.create("simple")
    assert isinstance(planner, SimplePlanner)


def test_planner_factory_creates_openai_planner(monkeypatch):
    monkeypatch.setattr("app.planners.factory.settings.llm_provider", "openai")
    monkeypatch.setattr("app.planners.factory.settings.openai_api_key", "test-key")
    planner = PlannerFactory.create("openai")
    assert isinstance(planner, LLMPlanner)


def test_planner_factory_falls_back_to_simple_without_api_key(monkeypatch):
    monkeypatch.setattr("app.planners.factory.settings.openai_api_key", None)
    planner = PlannerFactory.create("openai")
    assert isinstance(planner, SimplePlanner)


def test_planner_factory_rejects_unknown_planner():
    with pytest.raises(ValidationError):
        PlannerFactory.create("unknown")
