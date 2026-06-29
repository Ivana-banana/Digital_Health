"""Live LLM-адаптер: AI Studio через OpenAI-совместимый API (plan §5).

Свитч роли = другой URI (`PipelineConfig.models`). Провал схемы — типизированный
`SchemaError`, не исключение (для retry/деградации, plan §4).

Конфигурация через окружение (.env, не коммитить):
  OPENAI_BASE_URL        — base_url AI Studio (напр. https://ai.api.cloud.yandex.net/v1)
  YANDEX_API_KEY         — API-ключ сервисного аккаунта (роль ai.languageModels.user)
  YANDEX_FOLDER_ID       — folder_id (вшивается в URI модели: gpt://<folder>/<model>)
  LLM_MODEL              — (опц.) одна модель на все роли, напр. qwen3.6-35b-a3b/latest
  LLM_MAX_OUTPUT_TOKENS  — бюджет вывода; reasoning-модель тратит токены на «мысли»

В P0 не вызывается вживую (frozen-eval на StubLLM); включаем после заполнения .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from pydantic import BaseModel, ValidationError

from src.pipeline.config import ModelConfig
from src.ports import Message, ModelRole, Ok, SchemaError, Text


@dataclass
class AIStudioLLM:
    """Реализация `LLMPort` поверх AsyncOpenAI, нацеленного на AI Studio."""

    base_url: str
    api_key: str
    models: ModelConfig
    folder_id: str | None = None
    max_output_tokens: int | None = None

    @classmethod
    def from_env(cls, models: ModelConfig | None = None) -> AIStudioLLM:
        """Собрать адаптер из .env (имена переменных — как в шаблоне организаторов)."""
        from dotenv import load_dotenv

        load_dotenv()
        cfg = models or ModelConfig()
        # LLM_MODEL (если задан) переопределяет все роли — режим одной модели для теста.
        single = os.environ.get("LLM_MODEL")
        if single:
            cfg = replace(cfg, workhorse=single, reasoning=single, ru=single, long=single)
        max_tokens = os.environ.get("LLM_MAX_OUTPUT_TOKENS")
        return cls(
            base_url=os.environ["OPENAI_BASE_URL"],
            api_key=os.environ["YANDEX_API_KEY"],
            models=cfg,
            folder_id=os.environ.get("YANDEX_FOLDER_ID"),
            max_output_tokens=int(max_tokens) if max_tokens else None,
        )

    def _client(self):
        # Импорт и инстанцирование лениво: офлайн-тесты не тянут клиент/сеть.
        from openai import AsyncOpenAI

        return AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    def _model_uri(self, role: ModelRole) -> str:
        # AI Studio требует полный URI модели: gpt://<folder>/<model>/latest.
        uri = self.models.uri(role)
        if self.folder_id and not uri.startswith("gpt://"):
            return f"gpt://{self.folder_id}/{uri}"
        return uri

    async def complete(
        self,
        msgs: list[Message],
        *,
        schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        model_role: ModelRole = "workhorse",
    ) -> Ok | Text | SchemaError:
        kwargs: dict[str, object] = {
            "model": self._model_uri(model_role),
            "messages": msgs,
            "temperature": temperature,
        }
        if self.max_output_tokens:
            kwargs["max_tokens"] = self.max_output_tokens
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client().chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""

        if schema is None:
            return Text(content)
        try:
            return Ok(schema.model_validate_json(content))
        except ValidationError as e:
            return SchemaError(reason=str(e), raw=content)
