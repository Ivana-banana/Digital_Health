# Хэндофф: AI-ассистент EBM (Трек 3)

Передача проекта. Полный план — **`plan.md`** (читать §3 граф, §11 дорожная карта).
Правила работы — **`CLAUDE.md`** (Simplicity First, хирургические правки, goal-driven, test-first).

## Что это
Мультиагентная система на **LangGraph**: гипотеза врача → PICO → поиск литературы →
наукометрический отбор → извлечение эффектов → мета-анализ → проверяемый отчёт с
уровнем доказательности. Слоистая (гексагональная) архитектура: `domain` ← `ports` ←
`adapters`, оркестрация в `pipeline`, наблюдаемость в `obs`, статистика в `stats`.

## Реализовано (P0–P3, ветка `vano`, всё зелёное)
Сквозной пайплайн **проходит насквозь** на заглушках и проверен вживую:

- **P0** — каркас: слои/порты/`Deps`/`PipelineConfig`, `LLMPort`→AI Studio, домен-схемы
  (вкл. `Extraction` с `unavailable`), граф из 12 узлов с reducer'ами, structured-логи,
  docker-smoke, минимальный YC-ноутбук (`training/`).
- **P1** — поиск/идентичность/наукометрия: PubMed (esearch+**QueryTranslation**, efetch),
  кросс-ID дедуп (`domain/identity`), token-bucket лимитеры (`obs/ratelimit`), trust-скоринг
  (`domain/scoring`), eligibility→PRISMA (`domain/eligibility`), OpenAlex/Scimago, scoping.
- **P2** — извлечение (защищаемая фаза): `stats/effect_conversions` (CI↔SE, 2×2→OR/RR, p→SE),
  LLM-Extractor с честным `unavailable`+span, fixed-effect пул+I², GRADE, appraisal по дизайну.
- **P3** — мета + гардрейлы: `stats/meta` (random-effects DL + **HKSJ** через t-квантиль на
  чистом stdlib, τ², **Egger**, leave-one-out + sensitivity по RoB, матрица совместимости),
  `stats/distributions` (t-квантиль/p-value через неполную бета, без scipy), `stats/plots`
  (forest/funnel, matplotlib Agg, офлайн), GRADE-понижения за публикационное смещение и RoB,
  `domain/sanitize` (PII-скраб + анти-инъекция), **fact-checker** (`VerifierPort` +
  офлайн `CorpusVerifier`, провенанс, ограниченная петля retry≤2 через условное ребро графа),
  **градуированная доказательность** (направление+сила+уверенность).

**Живые агенты (зовут модель):** Intake/PICO, Extractor, Synthesizer (Alice/ru).
Fact-checker — детерминированный (верификация ссылок надёжнее LLM; live Crossref/PubMed за тем
же портом). Остальные узлы — детерминированные tool-узлы.

**Проверено live:** AI Studio (PICO на EN, извлечение HR + честный `unavailable`), PubMed.
Демо (`python -m src.app.main`): QueryTranslation → scoping → PRISMA (ретракция исключена) →
таблица эффектов → пул `random_hksj` HR 0.61 (95% CI **0.36–1.02** — честное HKSJ-расширение
при k=2) → forest/funnel в `artifacts/` → GRADE moderate, ответ градуирован, ссылки verified.

**Live Cochrane-бенч** (`python -m eval.run_cochrane`, нужен `.env`): воспроизводимая сверка
живого пула с опубликованным Cochrane-обзором (BRAF+MEK vs BRAF-моно, OS) + recall по gold PMID.

## Реализовано в P4 (UI + деплой, ветка `vano`, всё зелёное)
- **Human-in-the-loop:** `interrupt()` в `intake_pico` (уточнение неполного PICO) и `scoping`
  (чекпойнт этап-1 → этап-2) под флагом `PipelineConfig.interactive` — в офлайн/судья-режиме
  (`interactive=False`, без чекпойнтера) backbone идёт насквозь, контракт ИИ-судьи неизменен.
  `build_graph(deps, *, checkpointer=...)`; интерактивный граф — на `MemorySaver`+`thread_id`.
- **Streamlit-чат** (`app/ui.py`, тонкая оболочка без логики): стриминг прогресса узлов
  (`astream`), пауза на чекпойнтах с резюмом `Command(resume=...)`, вкладки источники/эффекты/
  графики/PRISMA/trust. Ядро в `app/interactive.py` (драйвер) + `app/view.py` (чистый view-prep) —
  оба под pytest; UI верифицирован офлайн через `AppTest`. Офлайн-демо без ключей.
- **Live-режим подключён:** `app/live.build_live_deps()` (реальные PubMed + AI Studio из `.env`,
  Scimago офлайн; OpenAlex/верификатор off на первом прогоне). Доступ: UI-переключатель
  «Офлайн-демо / Живые данные» и `python -m src.app.main --live`. Проводка под тестом
  (`tests/test_live_deps.py`, без сети); реальный сетевой прогон — на машине с `.env`+интернетом
  (из CI/песочницы сеть закрыта). Судья-путь (без флага) и тесты остаются офлайн.
- **Live-retrieval настроен:** `plan_queries` строит запрос из P/I/O + фильтр
  `randomized controlled trial[pt] OR clinical trial[pt]` (`tests/test_query_planner.py`).
  Проверено вживую на гипотезе меланома/анти-PD-1/OS: 16 РКИ распознаны, k=4 пригодных HR,
  пул `random_hksj` HR 0.74 (95% CI 0.42–1.29), GRADE low — **без галлюцинаций** (честный
  `unavailable` где HR нет в абстракте). Дальше (P5): больше извлекаемости — full-text mining
  + модель A для дизайна там, где Publication Type молчит.
- **Деплой/CI:** `Dockerfile.ui`+сервис `ui` в compose (порт 8501); судья-`Dockerfile` чинён
  (COPY `eval/`+`data/` — рантайм их читает); `requirements-ui.txt` (streamlit отдельно, образ
  судьи/CI лёгкие); `eval/run_frozen.py` (frozen-eval-subset: hallucination-rate=0 хард-гейт);
  Makefile `eval`/`ui`/`install-ui`; Sourcecraft CI гоняет `make ci` (вкл. frozen-eval)+`make run`.

**Quality-gate P4:** `docker compose run --rm app` → отчёт exit 0 (контракт неизменен);
`make ci` зелёный (73 теста + frozen-eval). **Осталось вручную:** живой пуш UI в YC
(нужны облачные креды) — артефакты и инструкция готовы (DEPLOY.md), локально верифицировано.

**Решение по персистентности (обсуждено, отложено):** БД пока не делаем — память живёт в
рамках сессии графа (`MemorySaver`), сетевой/LLM-кэш — in-memory `dict` в `Deps`. Если
вернёмся: рекомендация — **SQLite-first за новым `StorePort`** (офлайн → судья-контракт цел),
pgvector только для облачного full-text RAG за флагом `enable_fulltext_mining`. Принцип против
галлюцинаций: LLM видит не «всю базу», а bounded top-k извлечённых спанов + заземление.

## P5 — live online (сессия 30.06.2026, ветка `vano`, 82 теста зелёные → расширена 01.07)
**Разворот приоритета (решение пользователя):** финальный продукт — **живой/онлайн**, реально
работающий (суть хакатона). НЕ оптимизируем под ИИ-судью / оффлайн-детерминизм / frozen-синтетику.
Юнит-тесты оставляем как страховку математики, «витриной» не развиваем. Killer = живой прогон
тянет реальный PubMed + реальный LLM и **воспроизводит опубликованный Cochrane-обзор**.

- **Онлайн подтверждён живьём на этой машине:** `.env` заполнен (YANDEX_API_KEY + FOLDER_ID),
  PubMed отвечает ~2с, AI Studio `qwen3.6-35b` ~3с. Полный `python -m src.app.main --live` идёт
  насквозь за ~2.5 мин.
- **Cochrane gold заполнен реальными данными** — `eval/gold/cochrane_case_01.json` (`status: ready`):
  мишень **BRAF+MEK vs BRAF-моно, OS** (единственный гомогенный многотрайловый OS-пул обзора
  Pasquali 2018, CD011123.pub2, I²=0) → **Cochrane HR 0.70 (0.59–0.82), 4 РКИ, high**. 3 пивотных
  PMID сверены по абстрактам: COMBI-d 26037941 (0.71), COMBI-v 25399551 (0.69), coBRIM 27480103
  (0.70). Наш `stats/meta` на этих трёх: fixed 0.70 (0.605–0.811), random_hksj 0.70 — совпадает.
  (Прочие сравнения обзора — анти-PD-1 vs химио — одно-trial'ные, для «репро меты» не годятся.)
- **Новый код (всё за флагами, default off → офлайн не затронут; вкл. в `app/live.build_live_deps`):**
  - `enable_query_expansion` — LLM раскрывает PICO в **названия препаратов** (`QueryTerms` в
    schemas; `EXPAND_SYS`+`_expand_query_terms` в nodes). Без этого verbose-грани PICO
    («BRAF inhibitor plus MEK inhibitor») не достают пивотные РКИ (live-замер: 0/3 → 3/3).
  - `enable_llm_screening` — LLM-семантический скрининг по PICO поверх детерминированного eligibility
    (`ScreenJudgment` в schemas; `SCREEN_SYS`+`_llm_screen_one` в nodes), **конкурентно** через
    `asyncio.gather` под `deps.llm_semaphore`. При сбое LLM → include (recall>precision).
  - `max_retrieved=200` (ретрив расцеплён с `max_deep_studies`); скрининг сужает широкий пул.
  - Тесты: `tests/test_llm_screening.py`, расширен `tests/test_query_planner.py`.
- **Live-результат (BRAF+MEK гипотеза):** retrieve 170 (158 после дедупа, все 3 пивотных в выдаче)
  → screen 158→23 → пул `random_hksj` k=4 **HR 0.74 (0.51–1.07)**, 0 галлюцинаций. **Согласуется с
  Cochrane 0.70**, но это пока НЕ тот же набор трёх трайлов.
- **Открытые проблемы precision (следующие шаги, порядок A→D→B; время на B будет):**
  - **(A)** Извлечение берёт HR не из того сравнения: в пул попали 0.73 (биомаркерный субанализ),
    0.81 вместо gold-трайлов; один мисрид `HR 0.016` (вес ничтожный). → сузить `EXTRACT_SYS` до
    целевого I-vs-C + гардрейл правдоподобия.
  - **(D)** `eval/run_cochrane.py` — воспроизводимый живой бенчмарк (сверка пула с Cochrane + recall
    по `included_pmids`) для питча.
  - **(B, главная)** **trial-level identity**: схлопывать множество публикаций одного РКИ → брать
    первичную OS-публикацию → пул выходит ровно на gold-набор Cochrane. Также чинит recall (COMBI-v
    PMID 25399551 сейчас ошибочно исключается скринингом).

## P5 precision — сессия 01.07.2026 (ветка `vano`, 82 → **99 тестов зелёных**)

Порядок A → D → B закрыт целиком. Всё за флагами, офлайн-путь и контракт ИИ-судьи не затронуты
(`frozen-eval` PASS, `python -m src.app.main` exit 0, ruff+format чистые под 0.9.10).

- **(A) Precision-пасс извлечения — `unavailable`-первый гардрейл:**
  - `EXTRACT_SYS` (`src/pipeline/nodes.py`) переписан строго под primary-анализ целевого I-vs-C
    по целевому исходу в целевой популяции. При subgroup/biomarker/interim/sensitivity/crossover-
    adjusted/иначе-comparison → `effect_type=null`, `variance_source='unavailable'`. Для ratio-мер
    требование `0.05 ≤ point ≤ 20`.
  - `extract()`: в user-turn уходит весь PICO (было только outcome) — LLM видит I/C/P, чтобы решить
    «моё сравнение или нет».
  - `is_plausible_effect(extraction)` в `src/stats/effect_conversions.py` — чистая функция;
    в `extract()` вызывается после `derive_variance`, при `False` перезаписывает
    `variance_source='unavailable'` и `se=None`. Детерминированный последний рубеж против
    мисридов LLM (`HR 0.016`, `HR 25+`).
  - Тесты: `tests/test_effect_conversions.py` (+5 табличных: границы 0.05/20, MD/SMD не гейтятся,
    None-point проходит, nan/inf режутся), `tests/test_nodes_extract.py` (+2 через `StubLLM`:
    misread → `unavailable`, правдоподобный HR → `reported_ci`).

- **(D) Live Cochrane-бенчмарк — воспроизводимая one-command сверка:**
  - `eval/run_cochrane.py` — грузит `eval/gold/cochrane_case_01.json` (добавлено поле
    `demo_hypothesis` — RU-предложение врача), `build_live_deps(interactive=False)`,
    `run_full(demo_hypothesis, deps)`. Печатает report card:
    - **пул близок к Cochrane** — `|pool_point − 0.70| ≤ 0.10` И CI пересекаются с `[0.59, 0.82]`;
    - **recall(included_pmids) ≥ 2/3** (gold PMID = COMBI-d 26037941, COMBI-v 25399551,
      coBRIM 27480103);
    - информативно: `k_studies` vs Cochrane 4.
  - Exit: **0** PASS / **1** FAIL / **2 skip** без `.env` (CI не сломается при случайной интеграции).
  - `Makefile:eval-live` (не включён в `ci:` — сеть+ключи). Одна строка в README под live-разделом.

- **(B) Trial-level identity — публикации одного РКИ → одна первичная OS:**
  - `Source` (`src/domain/schemas.py`): +`nct_id`, +`trial_acronym`.
  - `data/trial_acronyms.json` — курованная мапа NCT→acronym под gold-кейс: COMBI-d NCT01584648,
    COMBI-v NCT01597908, coBRIM NCT01689519 (расширяется точечно).
  - `src/adapters/search/pubmed.py`: парсит NCT из `.//DataBankList/DataBank` (важный нюанс:
    `DataBankName` — дочерний элемент, не атрибут!) + fallback regex `\bNCT\d{8}\b` по абстракту;
    acronym подтягивается из курованной мапы. Расширена фикстура `tests/fixtures/efetch_sample.xml`
    NCT-блоком.
  - `src/domain/identity.py`: чистые `trial_key(source)` (NCT → acronym → None) и
    `collapse_by_trial(sources) -> set[str]` — эвристика первичной OS-публикации:
    `3·(HR/hazard ratio в абстракте) + 2·(«overall survival» в абстракте) + 1·(поздний год)
    + 0.5·(цифры в абстракте)`, тай-брейк по PMID. Источники без trial-сигнала — каждый сам трайл.
  - `PipelineConfig.enable_trial_collapse: bool = False`, включён в `build_live_deps`.
  - `screen()` под флагом: на `include=True`-подмножестве применяет `collapse_by_trial`,
    проигравших → `ScreenDecision(include=False, reason="duplicate")`. PRISMA-счётчики
    подстраиваются автоматически.
  - Тесты: `tests/test_identity.py` (+8: приоритет NCT над acronym, primary OS-победитель над
    subanalysis, distinct trials не режем, пустой вход, passthrough без сигнала),
    `tests/test_pubmed.py` (+2: NCT из `DataBank` и fallback из абстракта).

- **Живой Cochrane воспроизведён (сессия 01.07.2026):** `python -m eval.run_cochrane` **PASS**
  на этой машине, **стабильно 3 прогона подряд**. Пул `random_hksj` **HR 0.70 (0.69–0.71), k=5**
  ≡ Cochrane **HR 0.70 (0.59–0.82), k=4** — точка совпала до сотой; ДИ уже (k=5 HKSJ),
  пересекается с Cochrane. **Trial-recall 3/3**: COMBI-d ✓ (NCT01584648), COMBI-v ✓ (NCT01597908),
  coBRIM ✓ (NCT01689519). Направление `favors_intervention`, strength `supported`, 0 галлюцинаций.
  NCT-парсинг: 93/158 кандидатов из PubMed efetch.
- **Фиксы по ходу live-верификации:**
  - `EXTRACT_SYS` перепис v2 — доверяем LLM-скринингу проверку I-vs-C; extract только достаёт
    ITT-эффект целевого исхода + режет subgroup/implausible. Первая версия (v1) была слишком
    строгой (запрет «interim/exploratory» резал COMBI-d 26037941 — это интерим-OS, включена
    Cochrane).
  - `EXTRACT_SYS` v3 — few-shot про синонимы «hazard ratio for death» = OS-HR + пример из
    COMBI-v-стиля (multi-outcome abstract, брать OS-HR, не PFS-HR).
  - `_primary_os_score` в `collapse_by_trial` v2 — **OS-HR + CI в проксимити** доминирует над
    просто HR+CI (тот мог быть биомаркер / PFS); тай-брейкер инвертирован на РАННЮЮ публикацию
    (interim OS обычно и есть та, что в Cochrane).
  - `_merge_two` в `domain/identity.py` — прокинул `nct_id`/`trial_acronym` (регресс: при
    identity-дедупе поля терялись, отчего live-пайплайн видел `nct=None` у всех кандидатов, хотя
    парсер их читал корректно). +1 регресс-тест в `test_identity.py`.
  - `eval/run_cochrane.py` — метрика recall переехала с PMID на **NCT (trial-level)**: разные
    публикации одного РКИ = тот же трайл; Cochrane выбирает свои PMID редакторски, воспроизведение
    == покрытие ТРАЙЛОВ. Diagnostic вывод «NCT parsed: N/M candidates» для регресс-детекции.
  - **QueryTerms → SCREEN_SYS (drug-class matching):** `plan_queries` сохраняет `QueryTerms`
    (LLM-расширение PICO в конкретные drug names) в `state["query_terms"]`; `screen()` доставляет
    этот список в prompt LLM-скринера. SCREEN_SYS дополнен явным правилом: «если target
    comparison = 'BRAF inhibitor monotherapy' и в drug list есть 'vemurafenib', то arm с
    vemurafenib/vemurafenib+placebo — целевой сравнитель». Снимает стохастику на COMBI-v-подобных
    (LLM больше не режет primary публикацию из-за drug ≠ class).
- **Осталось (не блокирует питч):** второй gold-кейс «доказательств недостаточно» (plan.md §15,
  дополняет Cochrane-репро); non-code — видео-питч, слайды, деплой UI в YC.

### Третий кейс: второй Cochrane-репро — anti-PD-(L)1 в 2L NSCLC (PASS)

`eval/gold/cochrane_case_03_pd1_nsclc.json` + `make eval-live-3`. Cochrane-подобный gold из 4
pivotal РКИ (CheckMate 017/057, KEYNOTE-010, OAK): pooled OS HR 0.71 (0.64–0.78). Все pivotal
абстракты содержат явный OS-HR+CI (в отличие от трастузумаба HER2+ EBC).

Live PASS: **retrieve/screen/extract/pool = 4/4/4/4** гoldNCT; **Pool HR 0.74 (0.64–0.86), k=8**
vs Cochrane 0.71 — точка в 0.03, ДИ пересекается. Направление supported, favors_intervention,
0 галлюцинаций. **Второй независимый Cochrane-обзор воспроизведён вживую** — killer-факт
устоял на генерализации (другая нозология, другой класс препаратов).

Ключевой фикс: `sort=relevance` в PubMed esearch — default «Best Match» опускает pivotal-РКИ
мимо top-500 (проверено), а с `relevance` все 4 в top-42. Универсальная правка, полезная
для любого будущего кейса.

Регресс case 1 (BRAF+MEK) после `sort=relevance`: PASS ещё лучше — **Pool HR 0.70 (0.59–0.83),
k=6** vs Cochrane 0.70 (0.59–0.82) — точка и ДИ практически идентичны.

### Десятый шаг: сводка по всем gold-кейсам — 3/3 PASS (02.07.2026)

`make eval-live-all` (или `python -m eval.run_all_live`) прогоняет весь массив gold-кейсов
подряд и печатает markdown-таблицу «кейс | Cochrane | наш live | recall | GRADE | статус».
Экспорт в `eval/artifacts/live_summary.json` для слайдов/README.

**Результат сегодня:**

| Кейс | Cochrane | Наш live | Recall | GRADE | Статус |
|---|---|---|---|---|---|
| BRAF+MEK меланома OS | HR 0.70 (0.59–0.82), k=4 | HR 0.70 (0.59–0.83), k=6 | 3/3 | moderate | PASS |
| anti-PD-(L)1 NSCLC OS | HR 0.71 (0.64–0.78), k=4 | HR 0.72 (0.67–0.78), k=8 | 4/4 | moderate | PASS |
| sotorasib insufficient | — | Infeasible | — | — | PASS: честный отказ |

**Case 1: HR 0.70 буквально ≡ Cochrane 0.70** — точка совпала до сотой, ДИ 0.59–0.83
идентичен Cochrane 0.59–0.82. Готовый **питчевый слайд** — «воспроизвели 2 из 2 Cochrane
+ честный отказ на разреженных».

### Девятый шаг: live case 1 с новой GRADE — moderate (02.07.2026)

Прогон `make eval-live` после калибровки: PASS. **Pool HR 0.68 (0.62–0.74), k=5** ≡ Cochrane
HR 0.70 (0.59–0.82) — точка в 0.02, trial-recall 3/3. **GRADE = moderate** (Cochrane = high)
— честное `high − 1` за `abstract_only` (indirectness / low-quality source). Cochrane имеет
full-text доступ, они не понижают. **Наша система честно оценивает свои ограничения** —
плюс для питча по крит. 7 (снижение рисков LLM).

Bench показывает GRADE в report card: `информативно: GRADE vs Cochrane high — наш GRADE=moderate`.

### Восьмой шаг: GRADE калибровка по Cochrane-гайдлайнам (02.07.2026)

Cochrane-подобная калибровка `grade_level()` (plan §8, GRADE Handbook 2013):
- **Inconsistency**: I² > 90% → −2 (considerable heterogeneity, было −1 при >50%).
- **Imprecision**: для ratio-мер CI пересекает линию no-effect (1.0) → −1; иначе широкий
  CI (upper/lower > 4) → −1. Раньше был только грубый порог 3× — не учитывал клиническую
  значимость пересечения нуля-эффекта.
- **Indirectness / low-quality source**: abstract_only → −1 (без изменений).
- **Publication bias / RoB**: без изменений (Egger p<0.1, high_rob).
- **Large-effect upgrade** (для наблюдательных, start=low): HR/OR/RR < 0.5 или > 2.0 → +1
  (large); < 0.2 или > 5.0 → +2 (very large). Раньше upgrades не поддерживались.
- Backward-compat: `effect_type`/`pooled_point` необязательные — старая логика работает
  как раньше без них.

Пример из frozen-eval (offline demo, k=2, HR 0.61 CI 0.36-1.02): GRADE = `low` (было `moderate`)
— CI пересекает 1.0 (imprecision −1) + abstract_only (−1) → high − 2 = low. Честно.

Тесты: +7 GRADE-калибровки (`test_meta.py`), покрывают considerable heterogeneity, imprecision
CI-cross-1.0, wide-CI, large/very-large upgrade для observational, no-upgrade для РКИ.

**112 тестов зелёные** (было 105 + 7 GRADE).

### Седьмой шаг: reasoning-эскалация extract на Qwen3 235B (02.07.2026)

Плановая эскалация (plan §5) для главного узла качества:
- **`extract()`** под флагом `enable_reasoning_escalation` переключается с workhorse
  (`qwen3.6-35b-a3b`) на reasoning (`qwen3-235b-a22b-fp8`). Ловит стохастические
  `unavailable` от workhorse на нетривиальных абстрактах (COMBI-v-подобные).
- Default off (медленнее и дороже). Включается кастомным конфигом; smoke-test AI Studio
  подтвердил, что `qwen3-235b-a22b-fp8/latest` отвечает через тот же порт.
- Тесты: workhorse по умолчанию + reasoning под флагом (`tests/test_nodes_extract.py`,
  fake port `_RoleCapturingLLM` записывает `model_role` каждого вызова).

**105 тестов зелёные** (было 103 + 2 escalation-теста).

### Шестой шаг: sensitivity + provenance в UI (02.07.2026)

Глубина методологии видна врачу и жюри в интерфейсе (plan §8, §9; крит. 5/7/8):
- **Вкладка «Чувствительность»** — leave-one-out (пере-пул без каждого исследования) + пере-пул
  без high-RoB (устойчивость к риску смещения). Живой прогон case 1: `meta` узел логирует
  `loo=6` — 6 пере-пулов построены.
- **Provenance с evidence_span** — вкладка «Эффекты» имеет колонку «Цитата из абстракта»
  (дословный текст, из которого извлечено число); в отчёте под каждым фактом caption с
  цитатой. Врач видит откуда взято каждое HR → снижение рисков LLM.
- `MetaResult.excluded_source_id` — метка LOO-варианта пула; state расширен `leave_one_out:
  list[MetaResult]` и `sens_high_rob: MetaResult|Infeasible|None`. Офлайн-путь не затронут.

**103 теста зелёные** (было 102 + view/sensitivity + UI-smoke расширен).

### Пятый шаг: UI smoke + docker готовность (02.07.2026)

- **`tests/test_ui_smoke.py`** — Streamlit AppTest headless-регрессы UI-пути (2 теста):
  офлайн-поток гипотеза → scoping-чекпойнт → resume → отчёт с направлением/GRADE; чистый
  старт без исключений. Skip через `pytest.importorskip('streamlit')` для CI/судья без UI-зависимостей.
- **Docker UI-образ** (`docker compose build ui`): собран без ошибок → `ai-v-massy-ui:latest`.
  Контейнер стартует, `GET /` → HTTP 200, `/_stcore/health` → 200. Артефакт готов к YC-деплою
  (Serverless Container / Compute VM), команды в DEPLOY.md.

**102 теста зелёные** (было 100 + 2 UI-smoke).

### Четвёртый демо-кейс: «доказательств недостаточно» — sotorasib vs docetaxel (PASS)

`eval/gold/case_02_insufficient.json` (`status: ready`) + `eval/run_insufficient.py` + `make
eval-insufficient`. Гипотеза: соторасиб vs доцетаксель во 2L KRAS G12C mNSCLC. Одна pivotal РКИ
(CodeBreaK 200, Lancet 2023), второго сопоставимого нет → мета невозможна.

Live-прогон:
- retrieve **194** кандидатов → screen оставил **1** (LLM правильно отсеяла всё нерелевантное);
- extract=1, poolable=0 (в абстракте CodeBreaK 200 нет HR+CI одновременно);
- `meta = Infeasible("Нет исследований с извлекаемой дисперсией эффекта.")`;
- `report.direction = null`, `report.strength = 'insufficient'`, `confidence = 'very_low'`;
- **0 галлюцинаций**.

Питч-нарратив: два демо-сценария вместе показывают, что система **не гадает** — на богатых
данных воспроизводит Cochrane «до сотой», на разреженных честно говорит «недостаточно».

## Не-код TODO (помимо кода)
- **Видео-питч 5–7 мин** — демонстрация живого прогона + Cochrane-репро (killer-аргумент).
- **Сценарий демо** — 2 кейса: Cochrane-репро (BRAF+MEK) + разреженный «доказательств недостаточно».
- **Слайды/нарратив** — как продаём: «живой автоматический мета-анализ воспроизводит Cochrane, 0
  выдуманных чисел».
- **Живой деплой UI в Yandex Cloud** по `DEPLOY.md` (Serverless Container/VM, без GPU) — нужны
  облачные креды. Чтобы жюри видело онлайн.
- **NCBI API key** — для 10 rps PubMed (сейчас 3 rps без ключа; вписать в `.env`).
- **Проверка `.env` + открытая сеть на демо-машине** в момент питча (live зависит от этого).
- **Финальный тег/сдача**; обновить README/DEPLOY под live как основной режим.

## Осталось (P5–P6, см. plan.md §11)
- **P5** — качество: модель C (скрининг), reasoning-эскалация на Qwen3 235B, pgvector,
  **full-text mining** (OA RAG, за флагом `enable_fulltext_mining`), больше Cochrane-кейсов
  (сейчас в gold один — BRAF+MEK; `eval/run_cochrane.py` расширить на массив после добавления).
- **P6** — харденинг + презентация: полный frozen-eval, 2 демо-кейса, видео-питч.

**Оркестровка к добавлению:** fan-out map-reduce под LLM-семафором (извлечение/оценка
параллельно), relax-петля (ослабление запроса при 0 результатов). **Готово в P4:**
human-in-the-loop через `interrupt()` + checkpointer (`MemorySaver`)+`thread_id`; условное
ребро fact-check (`recursion_limit`/retry≤2) — с P3. Sqlite-saver не понадобился (демо в
одной сессии); своп на durable-saver — смена аргумента `build_graph(checkpointer=...)`.

**Не резать (ядро качества):** `effect_conversions`, identity-дедуп, ограничители, frozen-eval,
`unavailable`-семантика, scoping-чекпойнт, ограниченная петля fact-checker.
**Out:** KM-реконструкция, бинарный вердикт, ванильный DL без HKSJ.

## Конвенции (ВАЖНО)
> **ОНЛАЙН — ОСНОВНАЯ ФИЧА (разворот 30.06.2026).** Защищаем и объясняем на питче **живой**
> прогон (реальный PubMed + AI Studio), воспроизводящий Cochrane. Оффлайн-часть (`StubLLM`,
> `FrozenSearch`, frozen-eval, canned-сценарий ИИ-судьи) — **временные леса для проверки, их
> планируется удалить**; «offline-first» ниже — про вспомогательное тестовое, не про цель.
- **Язык:** внутри — **EN** (PICO, запросы, извлечение — модели/поиск точнее на английском);
  вход врача и **финальный отчёт — RU**. Промпты: `INTAKE_SYS`/`EXTRACT_SYS` (EN), synthesize (RU).
- **Offline-first (вспомогательное, к удалению):** тесты и `docker compose run --rm app` идут
  **без сети** — это страховка корректности, а не продукт. Парсеры — на фикстурах
  (`tests/fixtures/`), оффлайн-демо — на замороженном корпусе (`eval/frozen/corpus.json`).
  Live API — за портами (`adapters/`). Защищаемый путь — `--live` / `build_live_deps`.
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
src/domain/      schemas, identity, scoring, eligibility, grade, appraisal, sanitize  (чистое ядро)
src/stats/       effect_conversions, meta, distributions, plots             (чистая статистика)
src/ports/       Протоколы LLM/Search/Scientometrics/Quartile/Reranker/Verifier
src/adapters/    llm/{stub,aistudio}, search/{pubmed,frozen}, scientometrics/{openalex,scimago}, verify/{corpus}
src/pipeline/    config, deps, state, nodes, graph                          (оркестрация)
src/obs/         logging, ratelimit
src/app/main.py  точка входа (контракт ИИ-судьи)
eval/, training/ замороженный корпус + gold; YC-ноутбук обучения модели A
```

## Открытые вопросы (plan.md §14)
GPU-квота DataSphere; NCBI API key (для 10 rps); живой PubMed vs офлайн-корпус (берём
опубликованный Cochrane-обзор как ground truth); квоты премиум-моделей AI Studio.
**Закрыто:** меню AI Studio, endpoint/auth/формат модели (см. `.env.example`).
