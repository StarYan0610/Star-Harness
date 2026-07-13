from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.llm.base import LLMClient, LLMMessage


class OpenAIChatClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = base_url if base_url is not None else settings.openai_base_url
        self.model = model or settings.openai_model
        self.timeout_seconds = timeout_seconds or settings.openai_timeout_seconds
        self.temperature = settings.planner_temperature if temperature is None else temperature

    def complete_json(self, messages: list[LLMMessage]) -> str:
        if not self.api_key:
            raise ValidationError("OPENAI_API_KEY is required when DEFAULT_PLANNER=openai")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ValidationError("openai package is not installed; run `.venv/bin/pip install -e '.[test]'`") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout_seconds)
        response = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[{"role": message.role, "content": message.content} for message in messages],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValidationError("OpenAI planner returned empty content")
        return content

