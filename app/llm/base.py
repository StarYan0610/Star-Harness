from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, messages: list[LLMMessage]) -> str:
        raise NotImplementedError

