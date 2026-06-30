"""Проводка live-Deps (P4): реальные адаптеры собираются из .env, без сети.

Сеть не дёргается (клиенты ленивые) — проверяем только конструкцию: AI Studio LLM +
PubMed за портами, eval_mode=live, верификатор off, URI модели с folder_id.
"""

import dotenv

from src.adapters.llm.aistudio import AIStudioLLM
from src.adapters.search.pubmed import PubMedAdapter
from src.app.live import build_live_deps


def test_build_live_deps_wires_real_adapters(monkeypatch):
    # .env не читаем (тест гермётичен): no-op load_dotenv + явные переменные окружения.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ai.api.cloud.yandex.net/v1")
    monkeypatch.setenv("YANDEX_API_KEY", "test-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder123")
    monkeypatch.setenv("LLM_MODEL", "qwen3.6-35b-a3b/latest")
    monkeypatch.delenv("NCBI_API_KEY", raising=False)

    deps = build_live_deps(interactive=True)

    assert isinstance(deps.llm, AIStudioLLM)
    assert isinstance(deps.search, PubMedAdapter)
    assert deps.config.eval_mode == "live"
    assert deps.config.interactive is True
    assert deps.verifier is None  # источники из PubMed реальны; live-верификатор — на потом
    assert deps.scimago is not None  # квартили офлайн
    # LLM_MODEL переопределил роли; URI собирается с folder_id (gpt://<folder>/<model>)
    assert deps.llm._model_uri("ru").startswith("gpt://folder123/qwen3.6-35b-a3b")
