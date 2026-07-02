"""Модель A — классификатор дизайна (plan §7): заполняет только UNKNOWN + проводка в узел.

Энкодер/LR инжектятся fake-объектами → без torch/joblib в CI. Проверяем инвариант: RCT-метки
(из Publication Type) не перезаписываются — безопасность для зелёных Cochrane-кейсов.
"""

from __future__ import annotations

import asyncio

from src.adapters.classify.design_clf import DesignClassifier
from src.domain.schemas import Source, StudyDesign
from src.pipeline.deps import Deps
from src.pipeline.nodes import scientometrics


class _FakeEncoder:
    def encode(self, texts, normalize_embeddings=True):
        return [[float(len(t))] for t in texts]


class _FakeLR:
    """Всё классифицирует как observational (метка = значение enum)."""

    def predict(self, embeddings):
        return ["observational"] * len(embeddings)


def _classifier() -> DesignClassifier:
    clf = DesignClassifier()
    clf._model = _FakeEncoder()
    clf._clf = _FakeLR()
    return clf


def test_classify_fills_only_unknown_design():
    sources = [
        Source(pmid="1", title="RCT paper", design=StudyDesign.RCT),
        Source(pmid="2", title="No PT record", design=StudyDesign.UNKNOWN),
    ]
    out = asyncio.run(_classifier().classify(sources))
    assert out[0].design == StudyDesign.RCT  # PT-метка не тронута
    assert out[1].design == StudyDesign.OBSERVATIONAL  # UNKNOWN → предсказание модели


def test_classify_no_unknown_is_noop():
    sources = [Source(pmid="1", title="RCT", design=StudyDesign.RCT)]
    out = asyncio.run(_classifier().classify(sources))
    assert out == sources


class _StubClassifier:
    async def classify(self, sources):
        return [
            s.model_copy(update={"design": StudyDesign.RCT})
            if s.design == StudyDesign.UNKNOWN
            else s
            for s in sources
        ]


def test_scientometrics_uses_classifier_when_present():
    state = {"candidates": [Source(pmid="1", title="x", design=StudyDesign.UNKNOWN)]}
    deps = Deps(llm=None, classifier=_StubClassifier())  # type: ignore[arg-type]
    out = asyncio.run(scientometrics(state, deps))
    assert out["candidates"][0].design == StudyDesign.RCT


def test_scientometrics_passthrough_without_classifier():
    src = Source(pmid="1", title="x", design=StudyDesign.UNKNOWN)
    deps = Deps(llm=None)  # type: ignore[arg-type]
    out = asyncio.run(scientometrics({"candidates": [src]}, deps))
    assert out["candidates"][0].design == StudyDesign.UNKNOWN
