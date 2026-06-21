from app.planners.simple import SimplePlanner


def test_planner_generates_required_task_fields():
    plan = SimplePlanner().plan(
        run_id="550e8400-e29b-41d4-a716-446655440000",
        command="create",
        path="/tmp/demo",
        requirement="搭建项目",
        update_mode=None,
        audit_report=None,
        strategy_name="skeleton-first",
        strategy_text="strategy",
        max_tasks=2,
    )
    assert len(plan.tasks) == 2
    first = plan.tasks[0]
    assert first.task_id
    assert first.title
    assert first.description
    assert first.order_index == 1
    assert first.scope
    assert first.acceptance_criteria
    assert first.verification_commands


def test_planner_truncates_to_max_tasks():
    plan = SimplePlanner().plan(
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


def test_planner_creates_concrete_feature_tasks_from_requirement():
    plan = SimplePlanner().plan(
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
    titles = [task.title for task in plan.tasks]
    descriptions = [task.description for task in plan.tasks]
    assert "实现核心功能：健康检查接口" in titles
    assert "实现核心功能：README" in titles
    assert any("FastAPI" in item for item in plan.tasks[0].acceptance_criteria)
    assert all("第一组核心功能" not in description for description in descriptions)
