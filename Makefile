# Единый источник правды для проверок. CI вызывает эти же цели — то, что
# проходит локально (`make ci`), проходит и в пайплайне. Без секретов и сети.

.PHONY: install lint fmt fmt-check test build smoke run ci ci-docker

install:            ## Установить рантайм- и dev-зависимости
	pip install -r requirements.txt -r requirements-dev.txt

lint:               ## Статический анализ
	ruff check .

fmt:                ## Автоформат
	ruff format .

fmt-check:          ## Проверка форматирования (для CI)
	ruff format --check .

test:               ## Юнит-тесты
	pytest

build:              ## Сборка контейнера
	docker compose build

smoke:              ## Запуск решения в контейнере (exit 0 + маркер) — контракт судьи
	docker compose run --rm app

run:                ## Прямой запуск решения без docker (smoke для CI без DinD)
	python -m src.app.main

ci: lint fmt-check test        ## Быстрые проверки PR (без docker/секретов)

ci-docker: build smoke         ## Сборка образа + дымовой запуск в контейнере
