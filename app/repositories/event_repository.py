from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.event import Event


class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: Event) -> Event:
        self.session.add(event)
        return event
