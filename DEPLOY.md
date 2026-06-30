# Развёртывание для агента-оценщика

> Этот файл — **только для агента-оценщика**. Все шаги должны быть воспроизводимыми без ручных действий.

## Предусловия

- Docker Engine 24+
- Docker Compose v2 (`docker compose`)

## Сборка

```bash
docker compose build
```

## Запуск

```bash
docker compose run --rm app
```

## Проверки

Повторный запуск для проверки воспроизводимости:

```bash
docker compose run --rm app
```

## Критерии «всё работает»

- [ ] `docker compose build` завершается без ошибок
- [ ] `docker compose run --rm app` завершается с кодом `0`
- [ ] В stdout есть строка `Solution started`

Замените чеклист под своё решение, но оставьте **конкретные и проверяемые** критерии.

## Остановка и очистка

```bash
docker compose down --rmi local -v
```

---

## Демо-UI (Streamlit) — опционально

Чат врача со стримингом прогресса и human-in-the-loop чекпойнтами (уточнение PICO,
scoping этап-1 → этап-2). Офлайн-режим (StubLLM + замороженный корпус) работает без ключей.

```bash
docker compose up ui            # → http://localhost:8501
```

Образ UI (`Dockerfile.ui`) отделён от судья-образа, чтобы тот оставался лёгким.

## Деплой в Yandex Cloud (генерация по AI Studio API — GPU не нужен)

UI — это обычный веб-сервис; инференс идёт по AI Studio OpenAI-совместимому API,
поэтому GPU для демо не требуется (plan §12). Любой из путей:

- **Serverless Container:** собрать образ `Dockerfile.ui`, запушить в Container Registry,
  создать контейнер (порт `8501`), выдать публичный endpoint.
- **Compute VM:** `docker compose up -d ui` на ВМ с открытым портом `8501`.

**Секреты** (live-режим, мед-данные): задать в окружении контейнера, не в образе —
`YANDEX_API_KEY`, `YANDEX_FOLDER_ID`, `OPENAI_BASE_URL=https://ai.api.cloud.yandex.net/v1`
(шаблон — `config/.env.example`). Логирование запросов AI Studio — **выключить** (plan §5, §9).

## Frozen-eval (детерминированный quality-gate)

```bash
make eval                       # hallucination-rate=0, воспроизводимость пула — exit 0/1
```
