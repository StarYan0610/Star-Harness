from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.run import Run


class RunRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, run: Run) -> Run:
        self.session.add(run)
        return run

    def get(self, run_id: str) -> Run | None:
        return self.session.get(Run, run_id)
