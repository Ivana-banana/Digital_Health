"""Cross-encoder реранкер bge-reranker-v2-m3 за `RerankerPort` (модель B, plan §6.4).

`sentence-transformers` (CrossEncoder) импортируется **лениво** — judge/CI-образ без torch
(зависимость в `requirements-ml.txt`). Скорит пары (query, passage) и возвращает индексы
пассажей по убыванию релевантности: RAG-чанки (extract) и `title+abstract` кандидатов.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BGEReranker:
    """Реализация `RerankerPort`: ранжирование пассажей cross-encoder'ом."""

    model_name: str = "BAAI/bge-reranker-v2-m3"
    _model: object | None = field(default=None, repr=False)

    def _ensure(self) -> object:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    async def rerank(self, query: str, passages: list[str], *, top_n: int) -> list[int]:
        if not passages:
            return []
        model = self._ensure()
        scores = model.predict([(query, p) for p in passages])  # type: ignore[attr-defined]
        order = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)
        return order[:top_n]
