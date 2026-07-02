"""Скрининг-классификатор include/exclude за `ScreeningPort` (модель C, plan §7).

Обучен в YC DataSphere (`training/screening_clf.ipynb`): bi-encoder эмбеддинг PICO+источник +
LR-голова, чекпойнт `screening_clf.joblib`. Порог `threshold` низкий → **recall ≥ 0.95**
(не терять РКИ). Используется как recall-first второе мнение поверх LLM-скрининга.

`sentence-transformers`/`joblib` импортируются лениво (requirements-ml.txt) — judge/CI без torch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.domain.schemas import PICO, ScreenJudgment, Source

_SEP = " [SEP] "


def _pair_text(pico: PICO, source: Source) -> str:
    query = " ".join(
        t for t in [pico.population, pico.intervention, pico.comparison, pico.outcome] if t
    )
    return f"{query}{_SEP}{source.title}. {source.abstract or ''}"


@dataclass
class BiEncoderScreener:
    """Модель C: include/exclude по PICO с recall-first порогом."""

    checkpoint: Path | None = None
    model_name: str = "intfloat/multilingual-e5-small"
    threshold: float = 0.3  # низкий порог включения → высокий recall (не терять РКИ)
    _model: object | None = field(default=None, repr=False)
    _clf: object | None = field(default=None, repr=False)

    def _ensure(self) -> tuple[object, object]:
        if self._model is None or self._clf is None:
            import joblib
            from sentence_transformers import SentenceTransformer

            if not self.checkpoint or not Path(self.checkpoint).exists():
                raise FileNotFoundError(f"screening_clf checkpoint not found: {self.checkpoint}")
            self._model = SentenceTransformer(self.model_name)
            self._clf = joblib.load(self.checkpoint)
        return self._model, self._clf

    def _include_flags(self, clf: object, embeddings: object) -> list[bool]:
        """include, если P(include) ≥ threshold (recall-first); иначе — по метке predict."""
        if hasattr(clf, "predict_proba") and hasattr(clf, "classes_"):
            classes = list(clf.classes_)  # type: ignore[attr-defined]
            if "include" in classes:
                col = classes.index("include")
                probs = clf.predict_proba(embeddings)  # type: ignore[attr-defined]
                return [row[col] >= self.threshold for row in probs]
        preds = clf.predict(embeddings)  # type: ignore[attr-defined]
        return [str(p) == "include" for p in preds]

    async def screen(self, sources: list[Source], pico: PICO) -> list[ScreenJudgment]:
        if not sources:
            return []
        model, clf = self._ensure()
        texts = [_pair_text(pico, s) for s in sources]
        embeddings = model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
        flags = self._include_flags(clf, embeddings)
        return [
            ScreenJudgment(eligible=flag, reason="ok" if flag else "wrong_intervention")
            for flag in flags
        ]
