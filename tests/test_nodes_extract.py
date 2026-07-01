"""Precision-пасс `extract()`: гардрейл `is_plausible_effect` режет мисриды LLM (plan §9)."""

from __future__ import annotations

import asyncio

from src.adapters.llm.stub import StubLLM
from src.domain.identity import identity_key
from src.domain.schemas import PICO, Extraction, ScreenDecision, Source, StudyDesign
from src.pipeline.deps import Deps
from src.pipeline.nodes import extract


def _run_extract(canned: Extraction) -> Extraction:
    src = Source(
        pmid="99999999",
        title="Hypothetical trial",
        abstract="Abstract with some HR text.",
        design=StudyDesign.RCT,
    )
    state = {
        "pico": PICO(
            population="p",
            intervention="i",
            comparison="c",
            outcome="overall survival",
        ),
        "candidates": [src],
        "screening": [ScreenDecision(source_id=identity_key(src), include=True)],
    }
    deps = Deps(llm=StubLLM(canned={"Extraction": canned}))
    result = asyncio.run(extract(state, deps))
    return result["extractions"][0]


def test_extract_drops_implausible_hr_misread():
    # Реальный live-мисрид: LLM вернул `HR 0.016` из чужого контекста абстракта.
    # Детерминированный гардрейл переводит в `unavailable` — из пула вылетает.
    ex = _run_extract(
        Extraction(
            source_id="",
            effect_type="HR",
            point=0.016,
            ci_low=0.005,
            ci_high=0.05,
            evidence_span="mangled span",
        )
    )
    assert ex.variance_source == "unavailable"
    assert ex.se is None


def test_extract_keeps_plausible_hr():
    ex = _run_extract(
        Extraction(
            source_id="",
            effect_type="HR",
            point=0.70,
            ci_low=0.55,
            ci_high=0.90,
            evidence_span="HR 0.70 (95% CI 0.55-0.90)",
        )
    )
    assert ex.variance_source == "reported_ci"
    assert ex.se and ex.se > 0
