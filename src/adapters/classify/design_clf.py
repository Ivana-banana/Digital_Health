"""Классификатор дизайна исследования за `ClassifierPort` (модель A, plan §7).

Обучен в Yandex Cloud DataSphere (`training/design_clf_min.ipynb`): энкодер e5 + LR-голова,
чекпойнт `design_clf.joblib` из Object Storage. Заполняет `design` **только там, где PT молчит**
(`StudyDesign.UNKNOWN`) — «ценность там, где Publication Type молчит» (plan §7). RCT/обзоры и
т.п., уже определённые по Publication Type, не перезаписываются.

`sentence-transformers`/`joblib` импортируются лениво (requirements-ml.txt) — judge/CI без torch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.domain.schemas import Source, StudyDesign


def _to_design(label: str) -> StudyDesign:
    try:
        return StudyDesign(label)
    except ValueError:
        return StudyDesign.UNKNOWN


@dataclass
class DesignClassifier:
    """Модель A: предсказывает дизайн для источников с неизвестным дизайном."""

    checkpoint: Path | None = None
    model_name: str = "intfloat/multilingual-e5-small"
    _model: object | None = field(default=None, repr=False)
    _clf: object | None = field(default=None, repr=False)

    def _ensure(self) -> tuple[object, object]:
        if self._model is None or self._clf is None:
            import joblib
            from sentence_transformers import SentenceTransformer

            if not self.checkpoint or not Path(self.checkpoint).exists():
                raise FileNotFoundError(f"design_clf checkpoint not found: {self.checkpoint}")
            self._model = SentenceTransformer(self.model_name)
            self._clf = joblib.load(self.checkpoint)
        return self._model, self._clf

    async def classify(self, sources: list[Source]) -> list[Source]:
        idx = [i for i, s in enumerate(sources) if s.design == StudyDesign.UNKNOWN]
        if not idx:
            return sources
        model, clf = self._ensure()
        texts = [f"{sources[i].title}. {sources[i].abstract or ''}" for i in idx]
        embeddings = model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
        preds = clf.predict(embeddings)  # type: ignore[attr-defined]
        out = list(sources)
        for i, label in zip(idx, preds, strict=True):
            out[i] = sources[i].model_copy(update={"design": _to_design(str(label))})
        return out
