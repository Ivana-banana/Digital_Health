"""Плотный энкодер bge-m3 за `domain.fulltext.DenseEmbedder` (plan §6.4).

`sentence-transformers` импортируется **лениво** внутри `_ensure` — judge/CI-образ не тянет
torch (зависимость в `requirements-ml.txt`). Модель грузится один раз при первом `embed`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BGEM3Embedder:
    """Dense-векторы bge-m3 (нормированные) для чанков и запроса (RAG-гибрид, plan §6.4)."""

    model_name: str = "BAAI/bge-m3"
    _model: object | None = field(default=None, repr=False)

    def _ensure(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure()
        vecs = model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
        return [[float(x) for x in v] for v in vecs]
