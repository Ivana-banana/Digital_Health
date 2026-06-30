"""View-prep для UI (quality-gate P4): state → ViewModel вкладок, офлайн.

Гоняет демо-граф насквозь (StubLLM+frozen) и проверяет, что `build_view` отдаёт
ожидаемые строки источников/эффектов, PRISMA, пути графиков и trust-порядок.
"""

import asyncio

from src.app.main import DEMO_HYPOTHESIS, build_demo_deps, run_full
from src.app.view import build_view


def _view():
    final = asyncio.run(run_full(DEMO_HYPOTHESIS, build_demo_deps()))
    return build_view(final)


def test_view_sources_effects_and_prisma():
    vm = _view()

    # Источники отсортированы по trust (для trust-баров); 2 из 3 включены
    assert len(vm.sources) == 3
    assert [s.trust or 0 for s in vm.sources] == sorted(
        (s.trust or 0 for s in vm.sources), reverse=True
    )
    assert sum(s.included for s in vm.sources) == 2
    nejm = next(s for s in vm.sources if "England" in s.journal)
    assert nejm.quartile == "Q1" and nejm.trust and nejm.trust > 50
    assert all(s.label for s in vm.sources)  # ссылка-метка для проверяемости

    # Таблица эффектов: два HR с честным reported_ci и форматированным ДИ
    assert len(vm.effects) == 2
    assert {e.effect_type for e in vm.effects} == {"HR"}
    assert all(e.variance_source == "reported_ci" and "–" in e.ci for e in vm.effects)

    # PRISMA + QueryTranslation проброшены
    assert vm.prisma and vm.prisma.included == 2
    assert vm.query_translation


def test_view_meta_and_report():
    vm = _view()
    assert vm.meta and vm.meta.k_studies == 2
    assert 0.55 < vm.meta.pooled_point < 0.66
    assert vm.forest_path and vm.funnel_path  # пути графиков для вкладки
    assert vm.report and vm.report.direction == "favors_intervention"
    assert vm.report.confidence in ("high", "moderate", "low", "very_low")
