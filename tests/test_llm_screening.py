"""LLM-скрининг по PICO (узел `screen` за флагом `enable_llm_screening`).

Семантический фильтр гомогенности поверх детерминированного eligibility: исключает
кандидатов с другим сравнением/популяцией/исходом, чтобы мета не пулила разнородное.
При сбое/пустом ответе LLM кандидат остаётся (recall > precision). Флаг по умолчанию
выключен → офлайн/судья-путь не затронут.
"""

import asyncio

from src.adapters.llm.stub import StubLLM
from src.domain.identity import identity_key
from src.domain.schemas import PICO, ScreenJudgment, Source
from src.pipeline.config import PipelineConfig
from src.pipeline.deps import Deps
from src.pipeline.nodes import screen

PICO_TARGET = PICO(
    population="BRAF V600-mutant melanoma",
    intervention="BRAF + MEK inhibitor",
    comparison="BRAF inhibitor monotherapy",
    outcome="overall survival",
)
CANDIDATES = [
    Source(pmid="1", title="combo vs mono", abstract="dabrafenib + trametinib vs dabrafenib"),
    Source(pmid="2", title="combo vs chemo", abstract="vemurafenib + cobimetinib vs dacarbazine"),
    Source(pmid="3", title="no canned -> degrade", abstract="some melanoma trial"),
]


def _run(deps):
    return asyncio.run(screen({"candidates": CANDIDATES, "pico": PICO_TARGET}, deps))


def test_llm_screen_excludes_wrong_comparison_keeps_match():
    # canned: вкл, искл(wrong_intervention); третий — без canned → пустой ScreenJudgment.
    llm = StubLLM(
        canned_seq={
            "ScreenJudgment": [
                ScreenJudgment(eligible=True),
                ScreenJudgment(eligible=False, reason="wrong_intervention"),
            ]
        }
    )
    deps = Deps(llm=llm, config=PipelineConfig(enable_llm_screening=True))
    out = _run(deps)
    by_id = {d.source_id: d for d in out["screening"]}

    assert by_id[identity_key(CANDIDATES[0])].include is True
    excluded = by_id[identity_key(CANDIDATES[1])]
    assert excluded.include is False
    assert excluded.reason == "wrong_intervention"
    # третий: ответ LLM иссяк → пустой ScreenJudgment(eligible=True) → include (recall>precision)
    assert by_id[identity_key(CANDIDATES[2])].include is True

    prisma = out["prisma"]
    assert prisma.included == 2
    assert prisma.excluded_by_reason.get("wrong_intervention") == 1


def test_flag_off_keeps_deterministic_behavior():
    # Тот же canned-исключающий ответ, но флаг выключен → LLM не зовётся, все включены.
    llm = StubLLM(
        canned_seq={"ScreenJudgment": [ScreenJudgment(eligible=False, reason="wrong_outcome")]}
    )
    deps = Deps(llm=llm, config=PipelineConfig(enable_llm_screening=False))
    out = _run(deps)
    assert all(d.include for d in out["screening"])
    assert out["prisma"].included == len(CANDIDATES)
