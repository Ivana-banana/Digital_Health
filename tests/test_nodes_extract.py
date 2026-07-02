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


class _FullTextAwareLLM:
    """Fake LLMPort: абстракт → unavailable; при OS-HR в контексте (full-text) → HR 0.66."""

    async def complete(self, msgs, *, schema=None, temperature=0.0, model_role="workhorse"):
        from src.ports import Ok

        user = msgs[-1]["content"]
        if "0.66" in user:
            return Ok(
                Extraction(
                    source_id="",
                    effect_type="HR",
                    point=0.66,
                    ci_low=0.57,
                    ci_high=0.77,
                    evidence_span="hazard ratio for death was 0.66 (95% CI 0.57 to 0.77)",
                )
            )
        return Ok(Extraction(source_id="", variance_source="unavailable"))


class _FakeFullText:
    """Fake FullTextPort: Results с OS-HR, которого нет в абстракте (кейс трастузумаба)."""

    async def fetch(self, source):
        return (
            "Methods. Patients were randomly assigned to chemotherapy with or without trastuzumab."
            "\n\nResults. At 8 years, overall survival improved; the hazard ratio for death was "
            "0.66 (95% CI 0.57 to 0.77)."
        )


def _run_fulltext_extract(cfg: dict, *, fulltext=None) -> Extraction:
    src = Source(
        pmid="1",
        pmcid="PMC1",
        title="Trastuzumab trial",
        abstract="Disease-free survival improved (hazard ratio 0.64 for DFS).",
        design=StudyDesign.RCT,
    )
    from dataclasses import replace as _replace

    state = {
        "pico": PICO(
            population="p",
            intervention="trastuzumab",
            comparison="c",
            outcome="overall survival",
        ),
        "candidates": [src],
        "screening": [ScreenDecision(source_id=identity_key(src), include=True)],
    }
    llm = _FullTextAwareLLM()
    deps = Deps(llm=llm, config=_replace(Deps(llm=llm).config, **cfg), fulltext=fulltext)
    result = asyncio.run(extract(state, deps))
    return result["extractions"][0]


def test_extract_mines_fulltext_when_abstract_unavailable():
    """plan §6.4: абстракт даёт `unavailable` → OS-HR добирается из полного текста."""
    ex = _run_fulltext_extract({"enable_fulltext_mining": True}, fulltext=_FakeFullText())
    assert ex.variance_source == "reported_ci"
    assert ex.point == 0.66
    assert ex.text_source == "full_text"


def test_extract_no_fulltext_when_flag_off():
    """Флаг off → full-text не трогается, извлечение остаётся `unavailable`."""
    ex = _run_fulltext_extract({}, fulltext=_FakeFullText())
    assert ex.variance_source == "unavailable"
    assert ex.text_source == "abstract"


class _ReverseReranker:
    """Fake RerankerPort: разворачивает порядок пассажей (проверка приоритизации)."""

    async def rerank(self, query, passages, *, top_n):
        return list(reversed(range(len(passages))))[:top_n]


def test_extract_prioritizes_candidates_via_reranker():
    srcs = [
        Source(pmid="1", title="A", abstract="a", design=StudyDesign.RCT),
        Source(pmid="2", title="B", abstract="b", design=StudyDesign.RCT),
    ]
    state = {
        "pico": PICO(population="p", intervention="i", comparison="c", outcome="o"),
        "candidates": srcs,
        "screening": [ScreenDecision(source_id=identity_key(s), include=True) for s in srcs],
    }
    llm = StubLLM(canned={"Extraction": Extraction(source_id="", effect_type="HR", point=0.7)})
    deps = Deps(llm=llm, reranker=_ReverseReranker())
    result = asyncio.run(extract(state, deps))
    # Реранкер развернул порядок → первым извлекается второй кандидат (pmid=2).
    assert result["extractions"][0].source_id == identity_key(srcs[1])
