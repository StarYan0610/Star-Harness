from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Task


class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_all(self, tasks: list[Task]) -> None:
        self.session.add_all(tasks)

    def list_by_run(self, run_id: str) -> list[Task]:
        stmt = select(Task).where(Task.run_id == run_id).order_by(Task.order_index)
        return list(self.session.scalars(stmt))
