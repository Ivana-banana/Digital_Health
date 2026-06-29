"""Замороженный поиск из локального корпуса (plan §10, §12).

Реализует `SearchPort` без сети: отдаёт заранее сохранённые источники. Единый
корпус для canned-демо ИИ-судьи и eval-gold → детерминизм. Не зависит от живых API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.domain.schemas import Source
from src.ports import SearchResult


@dataclass
class FrozenSearch:
    """`SearchPort`-адаптер поверх фиксированного списка источников."""

    sources: list[Source]
    translation: str | None = None

    @classmethod
    def from_json(cls, path: str | Path) -> FrozenSearch:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            sources=[Source(**s) for s in data["sources"]],
            translation=data.get("translation"),
        )

    async def search(self, query: str, *, limit: int = 100) -> SearchResult:
        return SearchResult(sources=self.sources[:limit], translation=self.translation)
