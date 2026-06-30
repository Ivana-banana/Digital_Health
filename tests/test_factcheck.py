"""Тесты фактчекинга: верификация ссылок + ограниченная петля регенерации (plan §9)."""

import asyncio

from langgraph.graph import END

from src.adapters.llm.stub import StubLLM
from src.adapters.verify.corpus import CorpusVerifier
from src.domain.schemas import Claim, Report
from src.pipeline.deps import Deps
from src.pipeline.nodes import MAX_FACTCHECK_RETRIES, fact_check, route_after_factcheck


def _deps(valid_ids):
    return Deps(llm=StubLLM(), verifier=CorpusVerifier(valid_ids=set(valid_ids)))


def test_fact_check_drops_hallucinated_reference():
    """На терминальном проходе неподтверждённая ссылка выкидывается из отчёта (§9)."""
    report = Report(
        facts=[
            Claim(text="HR 0.6", type="fact", source_id="pmid:1"),
            Claim(text="HR 0.9", type="fact", source_id="pmid:hallucinated"),
        ]
    )
    state = {"report": report, "factcheck_retries": MAX_FACTCHECK_RETRIES}
    out = asyncio.run(fact_check(state, _deps({"pmid:1"})))
    facts = out["report"].facts
    assert [c.source_id for c in facts] == ["pmid:1"]  # галлюцинированная ссылка отброшена
    assert all(c.verified for c in facts)
    assert out["needs_regen"] is False


def test_fact_check_verifies_known_reference():
    report = Report(facts=[Claim(text="HR 0.6", type="fact", source_id="pmid:1")])
    out = asyncio.run(fact_check({"report": report}, _deps({"pmid:1"})))
    assert out["report"].facts[0].verified
    assert out["needs_regen"] is False


def test_fact_check_loop_is_bounded():
    """Неверифицируемая ссылка просит реген, пока retries<MAX, затем останавливается."""
    report = Report(facts=[Claim(text="x", type="fact", source_id="bad")])

    out1 = asyncio.run(fact_check({"report": report, "factcheck_retries": 0}, _deps(set())))
    assert out1["needs_regen"] is True
    assert out1["factcheck_retries"] == 1
    assert route_after_factcheck({"needs_regen": True}) == "synthesize"

    at_limit = {"report": report, "factcheck_retries": MAX_FACTCHECK_RETRIES}
    out2 = asyncio.run(fact_check(at_limit, _deps(set())))
    assert out2["needs_regen"] is False
    assert out2["report"].facts == []  # после лимита — выкинуть неподтверждённое
    assert route_after_factcheck({"needs_regen": False}) == END
