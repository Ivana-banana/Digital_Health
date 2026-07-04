# ИИ в массы — решение хакатона «Цифровое здоровье»

## Выбранное задание

**Задание:** 3 — AI-ассистент для научных исследований (клиническая онкология, EBM).

Полные формулировки и **открытые критерии оценки** — в [tasks/](tasks/).

## Обзор решения

Мультиагентная система на **LangGraph**: гипотеза врача → PICO → живой PubMed-поиск → отбор
и дедупликация РКИ (trial-level identity по NCT/acronym) → извлечение эффектов через LLM с
`unavailable`-семантикой (никаких выдуманных чисел) → мета-анализ (random-effects DL + HKSJ,
Egger, leave-one-out, sensitivity по RoB) → проверяемый отчёт с уровнем доказательности GRADE
и провенансом (evidence_span из абстракта под каждой цифрой).

**Killer-факт:** живой прогон **воспроизводит опубликованные Cochrane-обзоры до сотой** —
BRAF+MEK vs BRAF-моно (HR 0.70) и anti-PD-(L)1 vs docetaxel в 2L NSCLC (HR 0.72) —
и **честно отказывается** («доказательств недостаточно»), когда pivotal-РКИ одно.
Сводка живых результатов: [eval/artifacts/live_summary.json](eval/artifacts/live_summary.json).

**Хакатон:** [«Цифровое здоровье»](https://itmo.events/events/120684), 25 июня — 4 июля

## Документация

Бизнес-часть решения для оценки — в `docs/`:

- [overview.md](docs/overview.md) — проблема, цель, сценарии использования
- [architecture.md](docs/architecture.md) — архитектура и ключевые решения
- [data_schema.md](docs/data_schema.md) — данные и схемы

## Запуск и проверка

Воспроизводимое развёртывание для агента-оценщика — в [DEPLOY.md](DEPLOY.md).

**Основной режим — ОНЛАЙН (главная фича).** Живой прогон тянет реальный PubMed + реальный
LLM (Yandex AI Studio) и строит проверяемый отчёт; на gold-кейсе **воспроизводит опубликованный
Cochrane-обзор**. Это то, что мы защищаем на питче.

```bash
cp config/.env.example .env          # вписать YANDEX_API_KEY + YANDEX_FOLDER_ID
python -m src.app.main --live        # реальные PubMed + AI Studio → отчёт
make eval-live                       # live Cochrane-репро #1: BRAF+MEK меланома HR 0.70 (killer-факт)
make eval-live-3                     # live Cochrane-репро #2: anti-PD-(L)1 NSCLC HR 0.72 (генерализация)
make eval-insufficient               # live «доказательств недостаточно»: честный отказ (комплемент)
make eval-live-all                   # СВОДКА по всем кейсам — markdown-таблица для питча
# или UI-переключатель «Живые данные» в Streamlit-демо (ниже)
```

**Оффлайн-контракт ИИ-судьи** (вспомогательный, без сети/ключей — временные леса для проверки,
планируется удалить):

```bash
docker compose run --rm app          # печатает «Solution started» + ход анализа, exit 0
```

**Демо для врача (Streamlit-чат)** — гипотеза → PICO → поиск → мета-анализ → отчёт,
с human-in-the-loop чекпойнтами (уточнение PICO, scoping этап-1 → этап-2):

```bash
docker compose up ui                 # → http://localhost:8501
# или локально без docker:
make install-ui && make ui
```

**Локальные проверки (== CI):**

```bash
make install                         # рантайм + dev-зависимости
make ci                              # ruff + формат + pytest + frozen-eval
```

Деплой UI в Yandex Cloud (генерация по AI Studio API, GPU не нужен) — см. [DEPLOY.md](DEPLOY.md).

## Структура репозитория

Обязательные элементы (контракт для ИИ-судьи):

```
.
├── README.md              # этот файл: задание + обзор
├── DEPLOY.md              # команды для агента-оценщика
├── docker-compose.yml     # запуск в контейнерах
├── tasks/                 # копии всех заданий (справочник)
├── docs/                  # документация по решению
└── src/                   # код решения
```

Опционально: `requirements.txt`, `Dockerfile`, `config/`, `data/`, `assets/`, `ETHICS.md` и др.

## Лицензия

См. файл [LICENSE](LICENSE).

## Внесение вклада

См. файл [CONTRIBUTING.md](CONTRIBUTING.md).
