from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.time import naive_utcnow
from app.db.base import Base
from app.domain.enums import RunStatus


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    command: Mapped[str] = mapped_column(String, nullable=False)
    update_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_report_path: Mapped[str | None] = mapped_column(String, nullable=True)
    audit_report_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_name: Mapped[str] = mapped_column(String, nullable=False)
    plan_path: Mapped[str | None] = mapped_column(String, nullable=True)
    max_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    executor_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default=RunStatus.PENDING.value, nullable=False)
    current_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_task_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    failed_task_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=naive_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=naive_utcnow, onupdate=naive_utcnow, nullable=False)
