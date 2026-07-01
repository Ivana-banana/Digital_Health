# Промпт для следующей сессии (Трек 3, ветка `vano`)

Скопируй этот текст как стартовое сообщение новой сессии.

---

Я продолжаю хакатон-проект «AI-ассистент EBM для онкологии» (Трек 3, ветка `vano`).
Дедлайн питча — **04.07.2026**.

**ПРИОРИТЕТ (разворот 30.06.2026): ОНЛАЙН-РЕЖИМ — ОСНОВНАЯ ФИЧА.** Живой/онлайн прогон —
это то, что мы **защищаем и объясняем** на питче, суть хакатона. Killer-аргумент = живой
прогон тянет реальный PubMed + реальный LLM (AI Studio) и **воспроизводит опубликованный
Cochrane-обзор**. `.env` заполнен и проверен на этой машине — онлайн работает (PubMed ~2с,
AI Studio `qwen3.6-35b` ~3с).

**Оффлайн-часть** (`StubLLM`, `FrozenSearch`, frozen-eval, canned-сценарий ИИ-судьи) —
**временные леса только для проверки; их планируется полностью удалить.** НЕ оптимизируем под
ИИ-судью / оффлайн-детерминизм / frozen-синтетику и не развиваем их как «витрину». Юнит-тесты
чистых функций (`pytest`: `stats/`, конверсии, identity) ОСТАВЛЯЕМ как страховку корректности
математики — они делают живой результат доверенным.

Прежде чем что-либо делать:

1. **Прочитай** `HANDOFF.md` (что сделано/осталось), `plan.md` (§3 граф, §11 дорожная карта,
   §12 деплой) и `CLAUDE.md` (правила: Simplicity First, хирургические правки, test-first,
   явные assumptions, push back если есть проще).

2. **Подними окружение:** `.venv` уже есть → на Windows `.venv/Scripts/python.exe`, на Linux
   `.venv/bin/python` (проверено — работает). Проверь, что база зелёная:
   - `ruff check . && ruff format --check . && pytest` → **112 тестов зелёных**;
   - `python -m eval.run_frozen` → frozen-eval **PASS, exit 0** (хард-гейт hallucination-rate=0);
   - `python -m src.app.main` → «Solution started» + ход анализа, **exit 0** (контракт ИИ-судьи);
   - `python -m eval.run_cochrane` → live Cochrane-бенч (нужен `.env`; без `.env` — exit 2 skip);
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

8. **Сделано в сессии 01.07.2026 (P5 precision, ветка `vano`, 82 → 99 тестов зелёные):**
   Порядок A → D → B из предыдущей сессии закрыт целиком; всё за флагами, офлайн-путь и контракт
   ИИ-судьи не затронуты (frozen-eval PASS, `main` exit 0, UP-совместимо с ruff 0.9.10).
   - **(A) Precision-пасс извлечения:** `EXTRACT_SYS` (`src/pipeline/nodes.py`) переписан строго
     под целевое I-vs-C по целевому исходу в целевой популяции — при subgroup/biomarker/interim/
     sensitivity/crossover-adjusted/иначе-comparison → `effect_type=null`,
     `variance_source='unavailable'`. В `extract()` весь PICO уходит в user-turn (было только
     outcome). Детерминированный последний рубеж: `is_plausible_effect` в
     `src/stats/effect_conversions.py` — для HR/OR/RR требует `0.05 ≤ point ≤ 20`, режет мисриды
     `HR 0.016` и т.п. в `unavailable` (MD/SMD не гейтит). Тесты: `test_effect_conversions.py`
     (+5 табличных), `test_nodes_extract.py` (+2 через `StubLLM`).
   - **(D) Live Cochrane-бенчмарк:** `eval/run_cochrane.py` — воспроизводимый one-command
     (`make eval-live` или `python -m eval.run_cochrane`). Гоняет `build_live_deps` +
     `run_full(demo_hypothesis, deps)` на gold-PICO и печатает report card: «пул близок к
     Cochrane 0.70 (0.59–0.82)» (allow ±0.10 и CI-overlap) + `recall(included_pmids) ≥ 2/3`
     (gold=3). Exit 0 PASS / 1 FAIL / **2 skip** без `.env` (CI не сломается). В gold добавлен
     `demo_hypothesis` (RU-предложение врача). `Makefile:eval-live` (не в `ci:`). Одна строка в
     README под live-разделом.
   - **(B) Trial-level identity:** множество публикаций одного РКИ → одна первичная OS-публикация.
     - `Source` (`src/domain/schemas.py`): +`nct_id`, +`trial_acronym`.
     - `src/adapters/search/pubmed.py`: парсит NCT из `DataBankList/DataBank` (`DataBankName` —
       дочерний элемент, не атрибут!) + fallback regex `\bNCT\d{8}\b` по абстракту; acronym
       подтягивается из `data/trial_acronyms.json` (курованная мапа: COMBI-d NCT01584648,
       COMBI-v NCT01597908, coBRIM NCT01689519).
     - `src/domain/identity.py`: чистые `trial_key(source)` (NCT → acronym → None) и
       `collapse_by_trial(sources)` — эвристика первичной OS: `3·(HR в абстракте) + 2·(«overall
       survival») + 1·(поздний год) + 0.5·(цифры/n)`, тай-брейк по PMID; возвращает set
       `identity_key` победителей.
     - `PipelineConfig.enable_trial_collapse: bool = False`, включён в `build_live_deps`.
     - `screen()` под флагом: на `include=True`-подмножестве применить `collapse_by_trial`,
       проигравших → `include=False, reason="duplicate"` (PRISMA автоматически подстраивается).
     - Тесты: `test_identity.py` (+8: NCT/acronym-приоритеты, primary OS-победитель над
       субанализом, distinct trials не режем, пустой вход), `test_pubmed.py` (+2: NCT из
       `DataBank` и fallback из абстракта), фикстура `efetch_sample.xml` расширена NCT-блоком.

9. **Live-верификация Cochrane пройдена (01.07.2026, стабильно 3 прогона подряд):**
   `python -m eval.run_cochrane` **PASS**. Пул `random_hksj` **HR 0.70 (0.69–0.71), k=5** ≡
   Cochrane **HR 0.70 (0.59–0.82), k=4** — точка совпала до сотой; ДИ пересекается.
   **Trial-recall 3/3**: COMBI-d ✓ (NCT01584648), COMBI-v ✓ (NCT01597908), coBRIM ✓
   (NCT01689519). Направление `favors_intervention`, strength `supported`, 0 галлюцинаций.
   Ключевой фикс стабильности COMBI-v — прокинуть `QueryTerms` (drug names из query-expansion)
   в `SCREEN_SYS`: LLM теперь знает, что «vemurafenib = BRAF-моно», и не режет primary
   публикацию из-за drug ≠ class. Все фиксы — см. HANDOFF.md «P5 precision → Live Cochrane
   воспроизведён».

10. **Второй gold-кейс «доказательств недостаточно» готов и PASS live (01.07.2026):**
    `make eval-insufficient` → sotorasib vs docetaxel во 2L KRAS G12C mNSCLC. Одна pivotal РКИ
    (CodeBreaK 200), второго нет → `meta = Infeasible`, `report.strength='insufficient'`,
    `direction=null`, 0 галлюцинаций. Комплемент к Cochrane-репро: два демо-сценария вместе
    показывают, что система **не гадает**.

10a. **Второй Cochrane-репро (02.07.2026): anti-PD-(L)1 в 2L NSCLC — PASS live.**
     `make eval-live-3` → gold из 4 pivotal РКИ (CheckMate 017/057, KEYNOTE-010, OAK): pooled OS
     HR 0.71 (0.64–0.78). Live: **retrieve/screen/extract/pool = 4/4/4/4**, **Pool HR 0.74
     (0.64–0.86), k=8** vs Cochrane 0.71 — точка в 0.03, ДИ пересекается. **Второй независимый
     Cochrane воспроизведён вживую** — killer-факт устоял на генерализации (другая нозология,
     другой класс препаратов). Ключевой фикс: `sort=relevance` в PubMed esearch (default «Best
     Match» опускает pivotal-РКИ мимо top-500). Регресс case 1 (BRAF+MEK) после `sort=relevance`:
     **Pool HR 0.70 (0.59–0.83), k=6** vs Cochrane 0.70 (0.59–0.82) — точка идентична.

10b. **Отложенный gold-кейс — adjuvant трастузумаб HER2+ EBC (Cochrane Moja 2012):** абстракты
     pivotal-РКИ 2005 г. сообщают DFS, а не OS → требует **full-text mining** (флаг
     `enable_fulltext_mining`, план §6.4). Оставлен как задокументированный limitation в
     `eval/gold/cochrane_case_02_trastuzumab.json`.

10c. **UI smoke + docker готовность (02.07.2026):** `tests/test_ui_smoke.py` — Streamlit
     AppTest headless-регрессы UI-пути (полный офлайн-поток, чистый старт); Docker UI-образ
     `ai-v-massy-ui:latest` собран, контейнер стартует, `GET /` → HTTP 200, `/_stcore/health` →
     200. Артефакт готов к YC-деплою (Serverless Container / Compute VM).

10d. **Sensitivity + provenance в UI (02.07.2026):** новая вкладка «Чувствительность»
     (leave-one-out + пере-пул без high-RoB, план §8); в вкладке «Эффекты» — колонка «Цитата
     из абстракта» (evidence_span, план §9); в отчёте — caption-цитата под каждым фактом.
     Живой прогон case 1: `loo=6` (6 пере-пулов). Врач/жюри видят методологию и провенанс
     каждого числа → крит. 5/7/8.

10e. **Reasoning-эскалация extract на Qwen3 235B (02.07.2026):** `extract()` под флагом
     `enable_reasoning_escalation` переключается с workhorse (qwen3.6-35b-a3b) на reasoning
     (qwen3-235b-a22b-fp8). Default off (медленнее/дороже); smoke-test подтвердил, что
     reasoning-модель отвечает через AI Studio. Tests: `_RoleCapturingLLM` fake port
     проверяет model_role по флагу.

10f. **GRADE калибровка по Cochrane-гайдлайнам (02.07.2026):** `grade_level()` расширен:
     inconsistency I²>90% → −2 (considerable heterogeneity); imprecision ratio-мер CI
     пересекает 1.0 → −1; large-effect upgrade для наблюдательных (HR<0.5 → +1, <0.2 →
     +2). Backward-compat: старая сигнатура работает. Пример: offline demo с HR 0.61
     (CI 0.36-1.02) теперь `low` (было `moderate`) — CI пересекает 1.0 честно понижает.

11. **Следующие шаги:**
    - **Не-код (см. HANDOFF.md «Не-код TODO»):** видео-питч 5–7 мин; сценарий демо (2 кейса
      готовы); живой деплой UI в Yandex Cloud по `DEPLOY.md` (нужны облачные креды); NCBI API key
      (10 rps); слайды/нарратив; проверка `.env`+сети на демо-машине; финальный тег.
    - **Позже (если время):** больше Cochrane-кейсов; калибровка GRADE; reasoning-эскалация на
      Qwen3 235B; расширение `data/trial_acronyms.json` под новые gold-кейсы.

**Работай в ветке `vano`, test-first, после каждого шага гоняй**
`ruff check . && ruff format --check . && pytest`. Surgical changes — трогай только нужное.
Внутренняя коммуникация EN, отчёт/общение со мной RU. Сначала покажи краткий план следующей
фазы с проверками по каждому шагу, потом приступай. Если шаг требует решения — остановись и спроси.
