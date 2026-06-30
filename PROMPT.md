# Промпт для следующей сессии (Трек 3, ветка `vano`)

Скопируй этот текст как стартовое сообщение новой сессии.

---

Я продолжаю хакатон-проект «AI-ассистент EBM для онкологии» (Трек 3, ветка `vano`).
Дедлайн питча — **04.07.2026**.

**ПРИОРИТЕТ (разворот 30.06.2026): финальный продукт — ЖИВОЙ/ОНЛАЙН и реально
работающий — это суть хакатона.** НЕ оптимизируем под ИИ-судью, оффлайн-детерминизм и
frozen-синтетику. Юнит-тесты (`pytest`, чистая статистика/конверсии) ОСТАВЛЯЕМ как страховку
корректности математики (они делают живой результат доверенным), но «витриной» больше не
развиваем. Killer-аргумент = живой прогон тянет реальный PubMed + реальный LLM (AI Studio) и
**воспроизводит опубликованный Cochrane-обзор**. `.env` заполнен и проверен на этой машине —
онлайн работает (PubMed ~2с, AI Studio `qwen3.6-35b` ~3с).

Прежде чем что-либо делать:

1. **Прочитай** `HANDOFF.md` (что сделано/осталось), `plan.md` (§3 граф, §11 дорожная карта,
   §12 деплой) и `CLAUDE.md` (правила: Simplicity First, хирургические правки, test-first,
   явные assumptions, push back если есть проще).

2. **Подними окружение:** `.venv` уже есть → используй `.venv/Scripts/python.exe`. Проверь, что
   база зелёная:
   - `ruff check . && ruff format --check . && pytest` → **73 теста зелёных**;
   - `python -m eval.run_frozen` → frozen-eval **PASS, exit 0** (хард-гейт hallucination-rate=0);
   - `python -m src.app.main` → «Solution started» + ход анализа, **exit 0** (контракт ИИ-судьи);
   - UI: `make install-ui` затем `streamlit run src/app/ui.py` (офлайн-демо без ключей).

3. **Конвенции (ВАЖНО):** внутри пайплайна модели общаются на **английском**, отчёт и общение
   со мной — на **русском**; все тесты, `make ci`, `docker compose run --rm app` — **офлайн**
   (live-API только за портами `adapters/`, через `.env`/AI Studio); статистика/конверсии/
   identity/eligibility/scoring — **чистые функции**, LLM ничего не выдумывает (`unavailable`-
   семантика, провенанс, верификация ссылок). Лимиты на модели бесконечные — не экономь.

4. **Реализовано (P0–P4, всё зелёное, ветка `vano`):**
   - **P0** каркас: слои/порты/`Deps`/`PipelineConfig`, LangGraph-граф, structured-логи, docker-smoke.
   - **P1** поиск/идентичность/наукометрия/scoping (PubMed+QueryTranslation, dedup, trust, PRISMA).
   - **P2** извлечение+конверсии (`stats/effect_conversions`, Extractor с `unavailable`+span, GRADE).
   - **P3** мета+гардрейлы: `stats/meta` (random DL + HKSJ на чистом stdlib), Egger, leave-one-out,
     sensitivity по RoB, forest/funnel (matplotlib Agg), `sanitize` (PII+анти-инъекция),
     fact-checker (`VerifierPort`+`CorpusVerifier`, ограниченная петля retry≤2), градуированная
     доказательность.
   - **P4** UI+деплой: human-in-the-loop через `interrupt()` в `intake_pico`/`scoping` под флагом
     `PipelineConfig.interactive` (офлайн/судья-режим идёт насквозь, контракт неизменен);
     `build_graph(deps, *, checkpointer=...)` на `MemorySaver`+`thread_id`; Streamlit-чат
     (`app/ui.py` — тонкая оболочка; ядро в `app/interactive.py`+`app/view.py`, под pytest);
     `Dockerfile.ui`+сервис `ui`; чинён судья-`Dockerfile` (COPY eval/+data/); `requirements-ui.txt`;
     `eval/run_frozen.py` (frozen-eval-subset); Sourcecraft CI (`make ci` вкл. frozen-eval + `make run`).
     **Live-режим:** `app/live.build_live_deps()` (PubMed+AI Studio из `.env`) — UI-переключатель
     «Офлайн/Живые» и `python -m src.app.main --live`. Проводка под тестом без сети; реальный прогон —
     на машине с `.env`+интернетом. Судья-путь и тесты — офлайн.

5. **Решения по ходу (для контекста):**
   - **БД отложена** — память живёт в рамках сессии графа (`MemorySaver`), кэш — in-memory `dict`.
     Если вернёмся к персистентности: **SQLite-first за `StorePort`** (офлайн → судья цел),
     pgvector только для облачного full-text RAG за `enable_fulltext_mining`. Принцип против
     галлюцинаций: LLM видит bounded top-k извлечённых спанов, не «всю базу».
   - **Sqlite-saver не понадобился** (демо в одной сессии); своп на durable = смена аргумента
     `build_graph(checkpointer=...)`.

6. **Не резать (ядро качества):** `effect_conversions`, identity-дедуп, ограничители, frozen-eval,
   `unavailable`-семантика, scoping-чекпойнт, ограниченная петля fact-checker, hallucination-rate=0.
   **Out:** KM-реконструкция, бинарный вердикт, ванильный DL без HKSJ.

7. **Сделано в сессии 30.06.2026 (P5 live, ветка `vano`, 82 теста зелёные) — см. HANDOFF.md:**
   - **Онлайн подтверждён живьём:** PubMed + AI Studio отвечают; полный пайплайн `--live` идёт
     насквозь за ~2.5 мин и **воспроизводит Cochrane**.
   - **Cochrane gold заполнен реальными данными** (`eval/gold/cochrane_case_01.json`): мишень
     BRAF+MEK vs BRAF-моно, OS, **Cochrane HR 0.70 (0.59–0.82), 4 РКИ**; 3 пивотных PMID сверены
     по абстрактам. Наш `stats/meta` на этих трёх = 0.70 (копейка-в-копейку).
   - **Новый код (всё за флагами, вкл. в `app/live`):** LLM-расширение запроса в названия
     препаратов (`enable_query_expansion` — иначе verbose-PICO не достаёт пивотные РКИ);
     LLM-семантический скрининг по PICO (`enable_llm_screening`, конкурентно под семафором);
     `max_retrieved=200`. Офлайн-путь не затронут (флаги default off).
   - **Live-результат:** пул `random_hksj` HR **0.74 (0.51–1.07)** — согласуется с Cochrane 0.70,
     0 галлюцинаций. НО precision неидеальна (см. ниже).

8. **Следующие шаги (порядок A → D → B; время на B будет):**
   - **(A) Precision-пасс извлечения:** сузить `EXTRACT_SYS` строго до целевого сравнения I-vs-C +
     гардрейл правдоподобия эффекта (резать мисриды типа `HR 0.016` и субанализы). Сейчас в пул
     попадают «соседние» анализы (0.73 биомаркерный, 0.81) вместо gold-трайлов.
   - **(D) Воспроизводимый живой бенчмарк** `eval/run_cochrane.py`: гоняет live-пайплайн на gold-
     PICO и печатает сверку пула с Cochrane (для питча) + recall по `included_pmids`.
   - **(B) Trial-level identity** *(главная цель качества, время будет)*: схлопывать множество
     публикаций одного РКИ → брать первичную OS-публикацию. Это выводит пул ровно на gold-набор
     Cochrane (3 трайла). Сейчас этого нет → контаминация субанализами. Также чинит recall
     (COMBI-v PMID 25399551 сейчас ошибочно исключается скринингом).
   - Позже: больше Cochrane-кейсов в gold; калибровка GRADE; reasoning-эскалация на Qwen3 235B.

9. **Осталось НЕ кодом (см. HANDOFF.md «Не-код TODO»):** видео-питч 5–7 мин; сценарий демо
   (2 кейса: Cochrane-репро + разреженный «недостаточно»); живой деплой UI в Yandex Cloud по
   `DEPLOY.md` (нужны облачные креды); NCBI API key (10 rps); слайды/нарратив; проверка `.env`+
   сети на демо-машине; финальный тег.

**Работай в ветке `vano`, test-first, после каждого шага гоняй**
`ruff check . && ruff format --check . && pytest`. Surgical changes — трогай только нужное.
Внутренняя коммуникация EN, отчёт/общение со мной RU. Сначала покажи краткий план следующей
фазы с проверками по каждому шагу, потом приступай. Если шаг требует решения — остановись и спроси.
