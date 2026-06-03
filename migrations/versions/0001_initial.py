"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("command", sa.String(), nullable=False),
        sa.Column("update_mode", sa.String(), nullable=True),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=True),
        sa.Column("audit_report_path", sa.String(), nullable=True),
        sa.Column("audit_report_summary", sa.Text(), nullable=True),
        sa.Column("strategy_name", sa.String(), nullable=False),
        sa.Column("plan_path", sa.String(), nullable=True),
        sa.Column("max_tasks", sa.Integer(), nullable=False),
        sa.Column("executor_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_task_id", sa.String(), nullable=True),
        sa.Column("total_tasks", sa.Integer(), nullable=False),
        sa.Column("completed_task_ids", sa.JSON(), nullable=False),
        sa.Column("failed_task_ids", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("executor_type", sa.String(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("verification_commands", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("executor_exit_code", sa.Integer(), nullable=True),
        sa.Column("executor_log_path", sa.String(), nullable=True),
        sa.Column("review_status", sa.String(), nullable=True),
        sa.Column("review_summary", sa.Text(), nullable=True),
        sa.Column("review_findings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "order_index", name="uq_tasks_run_order"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("tasks")
    op.drop_table("runs")
