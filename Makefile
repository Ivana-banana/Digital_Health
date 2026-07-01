# Единый источник правды для проверок. CI вызывает эти же цели — то, что
# проходит локально (`make ci`), проходит и в пайплайне. Без секретов и сети.

.PHONY: install install-ui lint fmt fmt-check test eval eval-live build smoke run ui ci ci-docker

install:            ## Установить рантайм- и dev-зависимости
	pip install -r requirements.txt -r requirements-dev.txt

install-ui:         ## Доустановить зависимости Streamlit-UI
	pip install -r requirements-ui.txt

lint:               ## Статический анализ
	ruff check .

fmt:                ## Автоформат
	ruff format .

fmt-check:          ## Проверка форматирования (для CI)
	ruff format --check .

test:               ## Юнит-тесты
	pytest

eval:               ## Frozen-eval-subset — детерминированный quality-gate (plan §10)
	python -m eval.run_frozen

eval-live:          ## Live Cochrane-бенчмарк — сверка живого пула с gold (нужен .env)
	python -m eval.run_cochrane

build:              ## Сборка контейнера
	docker compose build

smoke:              ## Запуск решения в контейнере (exit 0 + маркер) — контракт судьи
	docker compose run --rm app

run:                ## Прямой запуск решения без docker (smoke для CI без DinD)
	python -m src.app.main

ui:                 ## Локальный запуск Streamlit-чата (нужен make install-ui)
	streamlit run src/app/ui.py

ci: lint fmt-check test eval    ## Быстрые проверки PR (без docker/секретов)

ci-docker: build smoke         ## Сборка образа + дымовой запуск в контейнере
