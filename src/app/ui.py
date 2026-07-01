"""Streamlit-чат врача (plan §3, §12): стриминг прогресса + human-in-the-loop.

Тонкая оболочка без бизнес-логики: драйвер графа — `app/interactive.py`, подготовка
вкладок — `app/view.py` (оба под pytest). Здесь — только рендер: ввод гипотезы,
стриминг узлов (`astream`), пауза на interrupt (уточнение PICO / scoping-чекпойнт)
с резюмом по `thread_id`, вкладки источники/эффекты/графики/PRISMA/trust.

Запуск (офлайн-демо, без ключей): `streamlit run src/app/ui.py`.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

# `streamlit run src/app/ui.py` кладёт в sys.path каталог скрипта, не корень → добавляем корень.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402
from langgraph.types import Command  # noqa: E402

from src.app.interactive import (  # noqa: E402
    build_session_graph,
    new_thread_config,
    pending_interrupt,
)
from src.app.live import build_live_deps  # noqa: E402
from src.app.main import DEMO_HYPOTHESIS, build_demo_deps  # noqa: E402
from src.app.view import (  # noqa: E402
    PICO_FIELDS,
    build_view,
    design_label,
    direction_label,
    grade_label,
    strength_label,
    variance_label,
)

# Внутри пайплайн — EN; интерфейс врача и отчёт — RU (plan §6.1).
DISCLAIMER = "Не является клинической рекомендацией; решение — за врачом."


async def _advance(graph, cfg, command) -> list[str]:
    """Прогнать граф до следующей паузы/конца, вернув имена отработавших узлов."""
    nodes: list[str] = []
    async for update in graph.astream(command, cfg):
        nodes.extend(update.keys())
    return nodes


def _run_segment(command) -> None:
    """Один сегмент между чекпойнтами: стрим прогресса узлов в статус-бар."""
    graph, cfg = st.session_state.graph, st.session_state.cfg
    with st.status("Анализ…", expanded=True) as status:
        for node in asyncio.run(_advance(graph, cfg, command)):
            status.write(f"✓ {node}")
        status.update(label="Сегмент завершён", state="complete")


def _start(hypothesis: str, live: bool) -> None:
    """Инициализировать сессию графа: офлайн-демо (StubLLM+корпус) или живые PubMed+AI Studio."""
    if live:
        deps = build_live_deps(interactive=True)  # реальные источники из .env
    else:
        deps = build_demo_deps()
        deps.config = replace(deps.config, interactive=True)
    st.session_state.graph = build_session_graph(deps)
    st.session_state.cfg = new_thread_config()
    _run_segment({"raw_hypothesis": hypothesis})


def _render_interrupt(value: dict) -> None:
    """Показать вопрос врачу и принять ответ → резюмировать граф (plan §3)."""
    if value.get("type") == "pico_clarification":
        st.warning("Не хватает данных для поиска — заполните недостающие поля и продолжите:")
        with st.form("pico_form"):
            answer = {}
            for f in value.get("missing", []):
                label, hint = PICO_FIELDS.get(f, (f, ""))
                answer[f] = st.text_input(label, key=f"pico_{f}", placeholder=hint, help=hint)
            submitted = st.form_submit_button("Продолжить поиск")
        if submitted:
            _run_segment(Command(resume=answer))
            st.rerun()
    elif value.get("type") == "scoping_checkpoint":
        s = value.get("summary", {})
        st.info(f"**Обзор поля (этап 1):** найдено {s.get('total_candidates', 0)} публикаций.")
        st.markdown("Разбивка по типу исследования:")
        for code, n in sorted(s.get("by_design", {}).items(), key=lambda kv: -kv[1]):
            st.markdown(f"- **{n}** — {design_label(code)}")
        st.caption(
            "РКИ — самый надёжный дизайн для вывода об эффекте; «дизайн не определён» означает, "
            "что тип не распознан по метаданным PubMed. Перейти к систематическому обзору и "
            "мета-анализу по этим публикациям?"
        )
        if st.button("Продолжить (этап 2)"):
            _run_segment(Command(resume={"proceed": True}))
            st.rerun()


def _render_report(vm) -> None:
    """Вкладки результата: отчёт/источники/эффекты/графики/PRISMA/trust/чувствительность."""
    tabs = st.tabs(
        ["Отчёт", "Источники", "Эффекты", "Графики", "PRISMA", "Trust", "Чувствительность"]
    )
    with tabs[0]:
        r = vm.report
        if r:
            st.markdown(
                f"**Направление эффекта:** {direction_label(r.direction)} · "
                f"**Уверенность вывода:** {strength_label(r.strength)}"
            )
            st.markdown(f"**Доказательность (GRADE):** {grade_label(r.confidence)}")
            if r.summary:
                st.write(r.summary)
            for c in r.facts:
                st.markdown(f"- {c.text}" + (f"  ↳ {c.source_id}" if c.source_id else ""))
                # Провенанс: дословная цитата из абстракта → врач проверяет число (plan §9).
                if c.span:
                    st.caption(f"  «{c.span}»")
        st.caption(DISCLAIMER)
    with tabs[1]:
        st.dataframe(
            [
                {
                    "Источник": s.label,
                    "Журнал": s.journal,
                    "Год": s.year,
                    "Дизайн": design_label(s.design),
                    "Q": s.quartile,
                    "Включён": "✓" if s.included else "",
                }
                for s in vm.sources
            ]
        )
        if vm.query_translation:
            st.caption(f"QueryTranslation: {vm.query_translation}")
    with tabs[2]:
        st.dataframe(
            [
                {
                    "Источник": e.source_id,
                    "Мера": e.effect_type,
                    "Оценка": e.point,
                    "95% CI": e.ci,
                    "Дисперсия": variance_label(e.variance_source),
                    "Цитата из абстракта": e.evidence_span,
                }
                for e in vm.effects
            ]
        )
        if vm.meta:
            m = vm.meta
            st.markdown(
                f"**Пул ({m.model}, k={m.k_studies}):** {m.effect_type} {m.pooled_point:.2f} "
                f"(95% CI {m.pooled_ci_low:.2f}–{m.pooled_ci_high:.2f}), I²={m.i_squared}%"
            )
    with tabs[3]:
        if vm.forest_path:
            st.image(vm.forest_path, caption="Forest plot")
        if vm.funnel_path:
            st.image(vm.funnel_path, caption="Funnel plot")
    with tabs[4]:
        if vm.prisma:
            p = vm.prisma
            st.write(
                {
                    "identified": p.identified,
                    "included": p.included,
                    "excluded": p.excluded,
                    "by_reason": p.excluded_by_reason,
                }
            )
    with tabs[5]:
        for s in vm.sources:
            st.write(s.label)
            st.progress(min(int(s.trust or 0), 100))
    with tabs[6]:
        _render_sensitivity(vm)


def _render_sensitivity(vm) -> None:
    """Sensitivity-анализ (plan §8): leave-one-out + пере-пул без high-RoB."""
    if not vm.sensitivity or not vm.meta:
        st.info("Sensitivity доступна только при собранном пуле.")
        return
    s = vm.sensitivity
    st.markdown(
        "Насколько устойчив пул к исключению одного исследования (leave-one-out) "
        "и к исключению исследований с высоким риском смещения (RoB)."
    )
    if s.leave_one_out:
        st.markdown("**Leave-one-out:** пул без каждого исследования")
        st.dataframe(
            [
                {
                    "Исключено": r.excluded_source_id or "—",
                    "Пул HR": round(r.pooled_point, 3),
                    "95% CI низ": round(r.pooled_ci_low, 3),
                    "95% CI верх": round(r.pooled_ci_high, 3),
                    "k": r.k_studies,
                }
                for r in s.leave_one_out
            ]
        )
    else:
        st.caption("Leave-one-out: k<3 в основном пуле — недостаточно исследований.")
    st.markdown("**Пере-пул без high-RoB:**")
    if s.high_rob_pooled_point is not None:
        st.markdown(
            f"HR {s.high_rob_pooled_point:.2f} (95% CI {s.high_rob_pooled_ci_low:.2f}–"
            f"{s.high_rob_pooled_ci_high:.2f}), k={s.high_rob_k_studies}"
        )
    st.caption(s.high_rob_note)


def main() -> None:
    st.set_page_config(page_title="EBM-ассистент (онкология)", layout="wide")
    st.title("AI-ассистент EBM · онкология")
    st.caption("Гипотеза врача → PICO → поиск → мета-анализ → проверяемый отчёт. " + DISCLAIMER)

    mode = st.radio(
        "Режим данных",
        ["Офлайн-демо (заглушка)", "Живые данные (PubMed + AI Studio)"],
        horizontal=True,
        help="Живой режим требует заполненный .env (ключи AI Studio). Офлайн — без ключей.",
    )
    live = mode.startswith("Живые")
    hypothesis = st.text_area("Гипотеза врача", value=DEMO_HYPOTHESIS, height=80)
    if st.button("Запустить анализ", type="primary"):
        try:
            _start(hypothesis, live)
        except Exception as exc:  # показать врачу понятную причину, не трейс
            st.error(f"Ошибка запуска ({'live' if live else 'офлайн'}): {exc}")
            st.stop()

    if "graph" not in st.session_state:
        return

    intr = pending_interrupt(st.session_state.graph, st.session_state.cfg)
    if intr is not None:
        _render_interrupt(intr.value)
    else:
        _render_report(build_view(st.session_state.graph.get_state(st.session_state.cfg).values))


if __name__ == "__main__":
    main()
