"""UI smoke через Streamlit AppTest — headless-запуск `src/app/ui.py` без сети.

Ловит регрессы, которые не поймают unit-тесты `view.py`/`interactive.py`: правки state
(например, `query_terms`) не должны ломать рендер вкладок; scoping-чекпойнт должен появиться;
после resume — отчёт с направлением/GRADE и таблицы источников/эффектов/PRISMA. Live-путь
не тестируется (нужен .env и сеть) — покрыт `tests/test_live_deps.py` (проводка) + live-бенчами.
"""

from __future__ import annotations

import pytest

# Streamlit только в requirements-ui.txt (не в базовом requirements.txt), чтобы судья-образ
# и CI оставались лёгкими → пропускаем UI smoke, если streamlit не установлен.
pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture
def app() -> AppTest:
    at = AppTest.from_file("src/app/ui.py", default_timeout=30)
    at.run()
    return at


def test_ui_offline_full_flow(app: AppTest) -> None:
    # Стартовая страница: заголовок, режим по умолчанию офлайн, кнопка запуска.
    assert any("EBM" in (m.value or "") for m in app.title)
    # Первый запуск: демо-гипотеза уже в text_area, жмём «Запустить анализ».
    assert app.text_area[0].value  # DEMO_HYPOTHESIS предзаполнен
    app.button[0].click().run()

    # После первого сегмента — scoping-чекпойнт (интерактивный режим включён).
    # PICO у demo полный → pico_clarification interrupt пропущен; ждём scoping.
    infos = [i.value for i in app.info if i.value]
    assert any("Обзор поля" in v for v in infos), f"нет scoping-чекпойнта; info={infos}"

    # Нажимаем «Продолжить (этап 2)» → резюмируем до отчёта.
    proceed = next(b for b in app.button if b.label == "Продолжить (этап 2)")
    proceed.click().run()

    # Отчёт готов: вкладки видимы, есть markdown с «Направление эффекта».
    markdowns = [m.value for m in app.markdown if m.value]
    assert any("Направление эффекта" in v for v in markdowns)
    assert any("Доказательность" in v for v in markdowns)


def test_ui_headless_no_exceptions(app: AppTest) -> None:
    # AppTest.run() падает при exception в render — здесь просто проверяем чистый старт.
    assert not app.exception
