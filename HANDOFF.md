# Хэндофф: AI-ассистент EBM (Трек 3)

Передача проекта. Полный план — **`plan.md`** (читать §3 граф, §11 дорожная карта).
Правила работы — **`CLAUDE.md`** (Simplicity First, хирургические правки, goal-driven, test-first).

## Что это
Мультиагентная система на **LangGraph**: гипотеза врача → PICO → поиск литературы →
наукометрический отбор → извлечение эффектов → мета-анализ → проверяемый отчёт с
уровнем доказательности. Слоистая (гексагональная) архитектура: `domain` ← `ports` ←
`adapters`, оркестрация в `pipeline`, наблюдаемость в `obs`, статистика в `stats`.

## Реализовано (P0–P2, ветка `vano`, всё зелёное)
Сквозной пайплайн **проходит насквозь** на заглушках и проверен вживую:

- **P0** — каркас: слои/порты/`Deps`/`PipelineConfig`, `LLMPort`→AI Studio, домен-схемы
  (вкл. `Extraction` с `unavailable`), граф из 12 узлов с reducer'ами, structured-логи,
  docker-smoke, минимальный YC-ноутбук (`training/`).
- **P1** — поиск/идентичность/наукометрия: PubMed (esearch+**QueryTranslation**, efetch),
  кросс-ID дедуп (`domain/identity`), token-bucket лимитеры (`obs/ratelimit`), trust-скоринг
  (`domain/scoring`), eligibility→PRISMA (`domain/eligibility`), OpenAlex/Scimago, scoping.
- **P2** — извлечение (защищаемая фаза): `stats/effect_conversions` (CI↔SE, 2×2→OR/RR, p→SE),
  LLM-Extractor с честным `unavailable`+span, `stats/meta` (fixed-effect пул+I²), GRADE
  (`domain/grade`), appraisal по дизайну (`domain/appraisal`).

**Живые агенты (зовут модель):** Intake/PICO, Extractor, Synthesizer. Остальные узлы —
детерминированные tool-узлы.

**Проверено live:** AI Studio (PICO на EN, извлечение HR + честный `unavailable`), PubMed.
Демо (`python -m src.app.main`): QueryTranslation → scoping → PRISMA (ретракция исключена) →
таблица эффектов → пул HR 0.61 (95% CI 0.51–0.73) → GRADE moderate.

## Осталось (P3–P6, см. plan.md §11)
- **P3** — мета + гардрейлы: random-effects (DerSimonian–Laird) + **HKSJ**, Egger, **forest/funnel**
  плоты, sensitivity (leave-one-out, по RoB); **fact-checker** (верификация каждого DOI/PMID,
  провенанс, регенерация только секции, retry≤2); **PII-скраб** + анти-инъекция; градуированная
  доказательность. LLM-агенты: Appraiser (reasoning), Meta-Interpreter, Fact-Checker.
- **P4** — UI/деплой: Streamlit `astream_events`+`interrupt()` (PICO-уточнение и scoping-чекпойнт),
  вкладки (источники/таблица/графики/PRISMA/trust), деплой в YC, Sourcecraft CI с frozen-eval.
- **P5** — качество: модель C (скрининг), reasoning-эскалация на Qwen3 235B, pgvector,
  **full-text mining** (OA RAG, за флагом `enable_fulltext_mining`), больше Cochrane-кейсов.
- **P6** — харденинг + презентация: полный frozen-eval, 2 демо-кейса, видео-питч.

**Оркестровка к добавлению:** fan-out map-reduce под LLM-семафором (извлечение/оценка
параллельно), checkpointer (Sqlite)+`thread_id`, условные ветки (relax-петля, fact-check
с `recursion_limit`), human-in-the-loop через `interrupt()`.

**Не резать (ядро качества):** `effect_conversions`, identity-дедуп, ограничители, frozen-eval,
`unavailable`-семантика, scoping-чекпойнт, ограниченная петля fact-checker.
**Out:** KM-реконструкция, бинарный вердикт, ванильный DL без HKSJ.

## Конвенции (ВАЖНО)
- **Язык:** внутри — **EN** (PICO, запросы, извлечение — модели/поиск точнее на английском);
  вход врача и **финальный отчёт — RU**. Промпты: `INTAKE_SYS`/`EXTRACT_SYS` (EN), synthesize (RU).
- **Offline-first:** все тесты и `docker compose run --rm app` (контракт ИИ-судьи) — **без сети**.
  Парсеры тестируются на фикстурах (`tests/fixtures/`), демо — на замороженном корпусе
  (`eval/frozen/corpus.json`). Live API — только за портами (`adapters/`).
- **Детерминизм ≠ генерация:** статистика/конверсии/eligibility/scoring/identity — чистые
  функции; LLM только извлекает и формулирует. Никаких выдуманных чисел (`unavailable`).
- **Модели — только AI Studio** (OpenAI-совместимый API), своп = смена URI. Qwen3.6 35B —
  workhorse; reasoning-модель и Alice (отчёт) — за ролями `LLMPort`.

## Запуск
```bash
python -m venv .venv && . .venv/Scripts/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
# проверки (== CI):
ruff check . && ruff format --check . && pytest
python -m src.app.main          # офлайн-демо, печатает Solution started + ход анализа
```
**Live-режим:** `cp config/.env.example .env`, вписать `YANDEX_API_KEY` + `YANDEX_FOLDER_ID`
(API-ключ сервисного аккаунта, роль `ai.languageModels.user`; `OPENAI_BASE_URL`=
`https://ai.api.cloud.yandex.net/v1`; модель `gpt://<folder>/<model>/latest` собирается
адаптером). `.env` в `.gitignore` — не коммитить.

## Карта кода
```
src/domain/      schemas, identity, scoring, eligibility, grade, appraisal  (чистое ядро)
src/stats/       effect_conversions, meta                                   (чистая статистика)
src/ports/       Протоколы LLM/Search/Scientometrics/Quartile/Reranker
src/adapters/    llm/{stub,aistudio}, search/{pubmed,frozen}, scientometrics/{openalex,scimago}
src/pipeline/    config, deps, state, nodes, graph                          (оркестрация)
src/obs/         logging, ratelimit
src/app/main.py  точка входа (контракт ИИ-судьи)
eval/, training/ замороженный корпус + gold; YC-ноутбук обучения модели A
```

## Открытые вопросы (plan.md §14)
GPU-квота DataSphere; NCBI API key (для 10 rps); живой PubMed vs офлайн-корпус (берём
опубликованный Cochrane-обзор как ground truth); квоты премиум-моделей AI Studio.
**Закрыто:** меню AI Studio, endpoint/auth/формат модели (см. `.env.example`).
