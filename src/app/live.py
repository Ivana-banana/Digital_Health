"""Сборка Deps для live-режима: реальные PubMed + AI Studio (plan §5, §6).

Конфигурация — из `.env` (ключи AI Studio/NCBI). Сеть живёт только здесь, за портами;
офлайн-путь (`StubLLM`+`FrozenSearch`, `app/main.build_demo_deps`) не затронут — он
остаётся контрактом ИИ-судьи и источником детерминизма для тестов.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.adapters.llm.aistudio import AIStudioLLM
from src.adapters.scientometrics.scimago import ScimagoTable
from src.adapters.search.pubmed import PubMedAdapter
from src.obs.ratelimit import RateLimiter
from src.pipeline.config import PipelineConfig
from src.pipeline.deps import Deps

ROOT = Path(__file__).resolve().parents[2]


def build_live_deps(*, interactive: bool = False, plots_dir: str | None = None) -> Deps:
    """Deps на живых источниках: AI Studio (LLM) + PubMed; Scimago-квартили офлайн.

    Требует заполненный `.env` (OPENAI_BASE_URL, YANDEX_API_KEY, YANDEX_FOLDER_ID, LLM_MODEL;
    опц. NCBI_API_KEY для 10 rps). OpenAlex-обогащение пока выключено — меньше точек отказа
    на первом live-прогоне (trust считается по дизайну+квартилю+свежести). Верификатор ссылок
    = None: источники приходят из PubMed (реальны); live Crossref/PubMed-верификатор — усиление
    на потом (plan §9).
    """
    from dotenv import load_dotenv

    load_dotenv()
    config = PipelineConfig(
        plots_dir=plots_dir or str(ROOT / "artifacts"),
        interactive=interactive,
        eval_mode="live",
        enable_llm_screening=True,  # семантический скрининг по PICO → гомогенный пул
        enable_query_expansion=True,  # расширение PICO → названия препаратов (live retrieval)
    )
    ncbi_key = os.environ.get("NCBI_API_KEY") or None
    return Deps(
        llm=AIStudioLLM.from_env(config.models),
        config=config,
        search=PubMedAdapter(limiter=RateLimiter(config.ncbi_rps), api_key=ncbi_key),
        scimago=ScimagoTable.load(ROOT / "data" / "scimago_quartiles.csv"),
        verifier=None,
    )
