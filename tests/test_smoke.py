"""Дымовой тест точки входа. Растёт вместе с кодом в P0+.

Контракт «решение запускается»: `python -m src.app.main` печатает маркер и
завершается без ошибок. Тот же маркер проверяет агент-оценщик (см. DEPLOY.md).
"""

from src.app.main import main


def test_main_prints_marker(capsys):
    main()
    assert "Solution started" in capsys.readouterr().out
