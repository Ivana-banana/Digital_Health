"""Offline-заглушка `LLMPort` (plan §10, §12).

Источник детерминизма для frozen-eval, юнит-тестов и canned-сценария ИИ-судьи:
без сети и ключей. Структурный ответ берётся: сначала из очереди `canned_seq`
по имени схемы (по одному на вызов — для fan-out извлечения), иначе из `canned`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from src.ports import Message, ModelRole, Ok, SchemaError, Text


@dataclass
class StubLLM:
    """Возвращает заранее заданные ответы; реализует `LLMPort` для офлайн-прогонов."""

    canned: dict[str, BaseModel] = field(default_factory=dict)
    canned_seq: dict[str, list[BaseModel]] = field(default_factory=dict)
    default_text: str = "[stub-summary]"

    async def complete(
        self,
        msgs: list[Message],
        *,
        schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        model_role: ModelRole = "workhorse",
    ) -> Ok | Text | SchemaError:
        if schema is None:
            return Text(self.default_text)
        name = schema.__name__
        seq = self.canned_seq.get(name)
        if seq:
            return Ok(seq.pop(0))
        canned = self.canned.get(name)
        if canned is not None:
            return Ok(canned)
        return Ok(schema())  # пустой валидный экземпляр — деградация, не падение
