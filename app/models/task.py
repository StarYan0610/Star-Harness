from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.time import naive_utcnow
from app.db.base import Base
from app.domain.enums import TaskStatus


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("run_id", "order_index", name="uq_tasks_run_order"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default=TaskStatus.PENDING.value, nullable=False, index=True)
    executor_type: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    verification_commands: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    executor_exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    executor_log_path: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    review_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_findings: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=naive_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=naive_utcnow, onupdate=naive_utcnow, nullable=False)
