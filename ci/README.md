# CI/CD — проверка кода на каждый PR

Цель: при каждом Pull Request в `main` автоматически проверять, что код **корректен и реально запускается**, до ревью и мёржа.

## Что проверяется (стадии)

| Стадия | Команда | Что валидирует | Секреты |
|---|---|---|---|
| Lint | `make lint` | стиль, импорты, баги (ruff) | нет |
| Format | `make fmt-check` | единый формат (ruff format) | нет |
| Tests | `make test` | юнит-тесты (pytest) | нет |
| Build | `make build` | образ собирается | нет |
| Smoke | `make smoke` | `docker compose run --rm app` → exit 0 + маркер (контракт агента-оценщика, см. [../DEPLOY.md](../DEPLOY.md)) | нет |

`make ci` = lint + fmt-check + test (быстрые). `make ci-docker` = build + smoke.

**Принцип:** CI **не требует секретов** (ключи YC/NCBI не нужны). Проверки идут **офлайн / на замороженных данных** (см. `eval` frozen-режим в [../plan.md](../plan.md) §10). Live-вызовы LLM/PubMed в PR-проверки не входят — это исключает флак и утечку ключей.

## Локально (то же, что в CI)

```bash
make install      # один раз
make ci           # быстрые проверки перед PR
make ci-docker    # сборка + дымовой запуск
```

Windows без `make`: выполнять команды из `Makefile` напрямую (`ruff check .`, `ruff format --check .`, `pytest`, `docker compose build`, `docker compose run --rm app`).

## Привязка к Sourcecraft

Триггер пайплайна — [`.sourcecraft/ci.yaml`](../.sourcecraft/ci.yaml). На каждый **PR в `main`** (и push в `main`) запускается workflow `pr-checks`: один cube на образе `python:3.11-slim` выполняет `make install → make ci → make run` (lint + формат + тесты + прямой запуск точки входа).

Заметки/допущения (проверить на первом прогоне):
- **Без DinD:** «код работает» проверяется прямым `python -m src.app.main`, а не `docker compose`. Контейнерный smoke (`make ci-docker`) гоняем локально и у агента-оценщика; добавим в CI отдельным workflow, если Sourcecraft даёт docker-in-docker.
- **Без секретов:** ключи YC/NCBI в PR-проверки не передаются (офлайн/frozen).
- Предполагается, что репозиторий доступен в рабочей директории cube автоматически (отдельного checkout-шага в схеме нет) — иначе добавим шаг клонирования.
- Образ тянется из Docker Hub; при зеркале реестра — заменить путь.
- **Чтобы CI заработал, `.sourcecraft/ci.yaml` должен сначала попасть в `main`** (конфиг читается из целевой ветки). Первый мёрж — разовый.
