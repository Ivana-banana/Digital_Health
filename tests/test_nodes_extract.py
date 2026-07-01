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


class _RoleCapturingLLM:
    """Fake LLMPort: записывает model_role каждого вызова для проверки эскалации."""

    def __init__(self, canned: Extraction) -> None:
        self.canned = canned
        self.roles: list[str] = []

    async def complete(self, msgs, *, schema=None, temperature=0.0, model_role="workhorse"):
        from src.ports import Ok

        self.roles.append(model_role)
        return Ok(self.canned)


def _run_extract_with_llm(llm, cfg) -> None:
    src = Source(
        pmid="1",
        title="Trial",
        abstract="HR 0.70",
        design=StudyDesign.RCT,
    )
    from dataclasses import replace as _replace

    state = {
        "pico": PICO(population="p", intervention="i", comparison="c", outcome="o"),
        "candidates": [src],
        "screening": [ScreenDecision(source_id=identity_key(src), include=True)],
    }
    deps = Deps(llm=llm, config=_replace(Deps(llm=llm).config, **cfg))
    asyncio.run(extract(state, deps))


def test_extract_uses_workhorse_by_default():
    llm = _RoleCapturingLLM(Extraction(source_id="", effect_type="HR", point=0.7))
    _run_extract_with_llm(llm, {})
    assert llm.roles == ["workhorse"]


def test_extract_escalates_to_reasoning_under_flag():
    """Reasoning-эскалация (plan §5): тяжёлый шаг extract идёт на Qwen3 235B под флагом."""
    llm = _RoleCapturingLLM(Extraction(source_id="", effect_type="HR", point=0.7))
    _run_extract_with_llm(llm, {"enable_reasoning_escalation": True})
    assert llm.roles == ["reasoning"]
