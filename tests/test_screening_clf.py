"""Модель C — скрининг-классификатор (plan §7): адаптер + recall-first спасатель в узле.

Энкодер/LR инжектятся fake-объектами → без torch/joblib в CI. Ключевой инвариант: модель C
только ВОЗВРАЩАЕТ РКИ, ошибочно исключённые LLM (recall-first), и не трогает ретракции/тип.
"""

from __future__ import annotations

import asyncio

from src.adapters.screen.biencoder_clf import BiEncoderScreener
from src.domain.schemas import PICO, ScreenJudgment, Source, StudyDesign
from src.pipeline.deps import Deps
from src.pipeline.nodes import screen
from src.ports import Ok

_PICO = PICO(population="p", intervention="i", comparison="c", outcome="o")


class _FakeEncoder:
    def encode(self, texts, normalize_embeddings=True):
        return [[float(len(t))] for t in texts]


class _PredictLR:
    def predict(self, embeddings):
        return ["include", "exclude"][: len(embeddings)]


def test_screener_predict_labels():
    scr = BiEncoderScreener()
    scr._model = _FakeEncoder()
    scr._clf = _PredictLR()
    out = asyncio.run(scr.screen([Source(title="a"), Source(title="bb")], _PICO))
    assert [j.eligible for j in out] == [True, False]


class _ProbaLR:
    classes_ = ["exclude", "include"]

    def predict_proba(self, embeddings):
        return [[0.6, 0.4], [0.95, 0.05]]


def test_screener_proba_threshold_favors_recall():
    scr = BiEncoderScreener(threshold=0.3)
    scr._model = _FakeEncoder()
    scr._clf = _ProbaLR()
    out = asyncio.run(scr.screen([Source(title="a"), Source(title="b")], _PICO))
    # P(include)=0.4 ≥ 0.3 → include; 0.05 < 0.3 → exclude.
    assert [j.eligible for j in out] == [True, False]


class _ExcludeByTitleLLM:
    """Fake LLMPort: LLM-скринер исключает источник с title 'EXCLUDE_ME'."""

    async def complete(self, msgs, *, schema=None, temperature=0.0, model_role="workhorse"):
        user = msgs[-1]["content"]
        if "EXCLUDE_ME" in user:
            return Ok(ScreenJudgment(eligible=False, reason="wrong_outcome"))
        return Ok(ScreenJudgment(eligible=True, reason="ok"))


class _IncludeAllScreener:
    async def screen(self, sources, pico):
        return [ScreenJudgment(eligible=True, reason="ok") for _ in sources]


def _run_screen(*, screener) -> list[bool]:
    from dataclasses import replace as _replace

    srcs = [
        Source(pmid="1", title="keep", abstract="a", design=StudyDesign.RCT),
        Source(pmid="2", title="EXCLUDE_ME", abstract="a", design=StudyDesign.RCT),
    ]
    llm = _ExcludeByTitleLLM()
    cfg = _replace(
        Deps(llm=llm).config, enable_llm_screening=True, enable_screening_clf=screener is not None
    )
    deps = Deps(llm=llm, config=cfg, screener=screener)
    out = asyncio.run(screen({"candidates": srcs, "pico": _PICO}, deps))
    return [d.include for d in out["screening"]]


def test_screening_clf_rescues_llm_excluded_rct():
    """Модель C возвращает РКИ, ошибочно исключённое LLM (recall-first, plan §7)."""
    assert _run_screen(screener=_IncludeAllScreener()) == [True, True]


def test_without_screener_llm_exclusion_stands():
    assert _run_screen(screener=None) == [True, False]
