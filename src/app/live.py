"""Сборка Deps для live-режима: реальные PubMed + AI Studio (plan §5, §6).

Конфигурация — из `.env` (ключи AI Studio/NCBI). Сеть живёт только здесь, за портами;
офлайн-путь (`StubLLM`+`FrozenSearch`, `app/main.build_demo_deps`) не затронут — он
остаётся контрактом ИИ-судьи и источником детерминизма для тестов.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.adapters.fulltext.europepmc import EuropePmcAdapter
from src.adapters.llm.aistudio import AIStudioLLM
from src.adapters.scientometrics.scimago import ScimagoTable
from src.adapters.search.pubmed import PubMedAdapter
from src.domain.fulltext import DenseEmbedder
from src.obs.ratelimit import RateLimiter
from src.pipeline.config import PipelineConfig
from src.pipeline.deps import Deps
from src.ports import ClassifierPort, RerankerPort, ScreeningPort

ROOT = Path(__file__).resolve().parents[2]

# Europe PMC REST — вежливый лимит; отдельный от NCBI token-bucket.
_EUROPEPMC_RPS = 5.0

# Чекпойнты моделей, обучаемых в YC → Object Storage → сюда (plan §7).
_DESIGN_CLF_PATH = ROOT / "data" / "models" / "design_clf.joblib"
_SCREENING_CLF_PATH = ROOT / "data" / "models" / "screening_clf.joblib"


def _try_ml_ports() -> tuple[DenseEmbedder | None, RerankerPort | None]:
    """bge-m3 эмбеддер + реранкер, если установлен `sentence-transformers` (requirements-ml.txt).

    Оба ленивые (модель грузится при первом вызове). Без ML-зависимостей → (None, None):
    full-text mining деградирует до BM25-only, приоритизация кандидатов — до trust (plan §6.4).
    """
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return None, None
    from src.adapters.embed.bge_m3 import BGEM3Embedder
    from src.adapters.rerank.bge_reranker import BGEReranker

    return BGEM3Embedder(), BGEReranker()


def _build_design_classifier() -> ClassifierPort | None:
    """Модель A, если чекпойнт скачан из Object Storage и `sentence-transformers` установлен.

    Нет чекпойнта / нет ML-зависимостей → None: узел `scientometrics` деградирует, дизайн
    остаётся из Publication Type (plan §7). Зелёные кейсы не затрагиваются до появления модели.
    """
    if not _DESIGN_CLF_PATH.exists():
        return None
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return None
    from src.adapters.classify.design_clf import DesignClassifier

    return DesignClassifier(checkpoint=_DESIGN_CLF_PATH)


def _build_screener() -> ScreeningPort | None:
    """Модель C (скрининг), если чекпойнт скачан и `sentence-transformers` установлен (plan §7)."""
    if not _SCREENING_CLF_PATH.exists():
        return None
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return None
    from src.adapters.screen.biencoder_clf import BiEncoderScreener

    return BiEncoderScreener(checkpoint=_SCREENING_CLF_PATH)


def build_live_deps(
    *, interactive: bool = False, plots_dir: str | None = None, fulltext: bool = False
) -> Deps:
    """Deps на живых источниках: AI Studio (LLM) + PubMed; Scimago-квартили офлайн.

    Требует заполненный `.env` (OPENAI_BASE_URL, YANDEX_API_KEY, YANDEX_FOLDER_ID, LLM_MODEL;
    опц. NCBI_API_KEY для 10 rps). OpenAlex-обогащение пока выключено — меньше точек отказа
    на первом live-прогоне (trust считается по дизайну+квартилю+свежести). Верификатор ссылок
    = None: источники приходят из PubMed (реальны); live Crossref/PubMed-верификатор — усиление
    на потом (plan §9).

    `fulltext=True` включает full-text mining (plan §6.4): Europe PMC OA-fetch + bge-m3/реранкер
    (если установлены). Нужен для кейсов, где эффект есть только в полном тексте (трастузумаб).
    """
    from dotenv import load_dotenv

    load_dotenv()
    screener = _build_screener()
    config = PipelineConfig(
        plots_dir=plots_dir or str(ROOT / "artifacts"),
        interactive=interactive,
        eval_mode="live",
        enable_llm_screening=True,  # семантический скрининг по PICO → гомогенный пул
        enable_query_expansion=True,  # расширение PICO → названия препаратов (live retrieval)
        enable_trial_collapse=True,  # публикации одного РКИ → одна первичная OS (plan §6.2)
        enable_fulltext_mining=fulltext,  # OA full-text RAG — для кейсов без эффекта в абстракте
        enable_screening_clf=screener is not None,  # модель C — recall-first второе мнение
    )
    ncbi_key = os.environ.get("NCBI_API_KEY") or None
    embedder, reranker = _try_ml_ports() if fulltext else (None, None)
    return Deps(
        llm=AIStudioLLM.from_env(config.models),
        config=config,
        search=PubMedAdapter(limiter=RateLimiter(config.ncbi_rps), api_key=ncbi_key),
        scimago=ScimagoTable.load(ROOT / "data" / "scimago_quartiles.csv"),
        classifier=_build_design_classifier(),
        screener=screener,
        fulltext=EuropePmcAdapter(limiter=RateLimiter(_EUROPEPMC_RPS)) if fulltext else None,
        embedder=embedder,
        reranker=reranker,
        verifier=None,
    )
