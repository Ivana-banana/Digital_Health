"""Чистая подготовка данных для вкладок UI (plan §8 UX).

`build_view(state)` превращает финальное (или промежуточное) состояние графа в
плоскую `ViewModel`: источники+trust, таблица эффектов, PRISMA, графики, отчёт.
Без импорта Streamlit и без I/O — тестируется обычным pytest; Streamlit-оболочка
лишь рендерит готовые поля.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.domain.identity import identity_key
from src.domain.schemas import (
    PICO,
    Extraction,
    Infeasible,
    MetaResult,
    PrismaCounts,
    Report,
    ScopingSummary,
    Source,
)

# Человекочитаемые подписи дизайна исследования (RU) — сырые коды enum не показываем врачу.
DESIGN_LABELS = {
    "rct": "РКИ (рандомизированное контролируемое исследование)",
    "non_randomized": "Нерандомизированное исследование",
    "observational": "Наблюдательное исследование",
    "review": "Обзор",
    "meta_analysis": "Мета-анализ",
    "case_report": "Клинический случай",
    "other": "Другой дизайн",
    "unknown": "Дизайн не определён",
}

# Грани PICO для формы уточнения: (подпись, подсказка-пример) — понятный ввод вместо англ. кода.
PICO_FIELDS = {
    "population": ("Популяция (пациенты)", "напр. метастатическая меланома"),
    "intervention": ("Вмешательство (терапия)", "напр. анти-PD-1"),
    "comparison": ("Сравнение (контроль)", "напр. химиотерапия"),
    "outcome": ("Исход", "напр. общая выживаемость"),
}


def design_label(code: str) -> str:
    """Код дизайна → читаемая подпись (RU); неизвестный код возвращаем как есть."""
    return DESIGN_LABELS.get(code, code)


# Подписи градуированной доказательности и источника дисперсии (RU) — не показываем коды врачу.
DIRECTION_LABELS = {
    "favors_intervention": "в пользу терапии",
    "favors_control": "в пользу контроля",
    "no_effect": "нет эффекта",
}
STRENGTH_LABELS = {
    "supported": "подтверждается",
    "uncertain": "вывод неуверенный",
    "insufficient": "доказательств недостаточно",
}
GRADE_LABELS = {
    "high": "высокая",
    "moderate": "умеренная",
    "low": "низкая",
    "very_low": "очень низкая",
}
VARIANCE_LABELS = {
    "reported_ci": "ДИ из статьи",
    "reported_se": "SE из статьи",
    "derived_2x2": "из таблицы 2×2",
    "derived_p": "из p-значения",
    "unavailable": "не сообщено",
}


def _label(table: dict[str, str], value: str | None) -> str:
    """Перевести код в RU-подпись; None/неизвестное → прочерк/как есть."""
    if not value:
        return "—"
    return table.get(value, value)


def direction_label(value: str | None) -> str:
    return _label(DIRECTION_LABELS, value)


def strength_label(value: str | None) -> str:
    return _label(STRENGTH_LABELS, value)


def grade_label(value: str | None) -> str:
    return _label(GRADE_LABELS, value)


def variance_label(value: str | None) -> str:
    return _label(VARIANCE_LABELS, value)


@dataclass(frozen=True)
class SourceRow:
    """Строка вкладки «Источники» / «Trust»: метка-ссылка + наукометрия."""

    label: str  # PMID/DOI/заголовок — для проверяемости (крит. 2)
    title: str
    journal: str
    year: int | None
    design: str
    quartile: str | None
    trust: float | None
    included: bool


@dataclass(frozen=True)
class EffectRow:
    """Строка таблицы эффектов: честная семантика variance_source (plan §0.2).

    `evidence_span` — дословная цитата из абстракта, обосновывающая число (провенанс,
    plan §9). Врач видит откуда взято число → снижение рисков LLM (крит. 7).
    """

    source_id: str
    effect_type: str | None
    point: float | None
    ci: str  # "0.44–0.77" либо "" если не сообщён
    variance_source: str
    evidence_span: str = ""


@dataclass(frozen=True)
class LOORow:
    """Строка leave-one-out: пере-пул без одного исследования (plan §8 sensitivity)."""

    excluded_source_id: str | None
    pooled_point: float
    pooled_ci_low: float
    pooled_ci_high: float
    k_studies: int


@dataclass(frozen=True)
class SensitivityView:
    """Все sensitivity-варианты пула для UI (plan §8): LOO + без high-RoB."""

    leave_one_out: list[LOORow] = field(default_factory=list)
    high_rob_pooled_point: float | None = None
    high_rob_pooled_ci_low: float | None = None
    high_rob_pooled_ci_high: float | None = None
    high_rob_k_studies: int | None = None
    high_rob_note: str = ""  # «нет high-RoB» / «мета невозможна без high-RoB»


@dataclass(frozen=True)
class ViewModel:
    """Плоская модель для рендера вкладок (источники/эффекты/графики/PRISMA/trust)."""

    hypothesis: str
    pico: PICO | None
    query_translation: str | None
    scoping: ScopingSummary | None
    sources: list[SourceRow] = field(default_factory=list)
    effects: list[EffectRow] = field(default_factory=list)
    prisma: PrismaCounts | None = None
    meta: MetaResult | None = None  # None, если мета невозможна/отсутствует
    forest_path: str | None = None
    funnel_path: str | None = None
    sensitivity: SensitivityView | None = None
    report: Report | None = None


def _source_label(s: Source) -> str:
    return s.pmid or s.doi or s.title or "—"


def _ci(e: Extraction) -> str:
    if e.ci_low is None or e.ci_high is None:
        return ""
    return f"{e.ci_low}–{e.ci_high}"


def build_view(state: Mapping) -> ViewModel:
    """Собрать ViewModel из состояния графа (чистая трансформация, без I/O)."""
    candidates: list[Source] = list(state.get("candidates", []))
    included = {d.source_id for d in state.get("screening", []) if d.include}
    sources = [
        SourceRow(
            label=_source_label(s),
            title=s.title,
            journal=s.journal or "",
            year=s.year,
            design=s.design.value,
            quartile=s.sjr_quartile,
            trust=s.trust_score,
            included=identity_key(s) in included,
        )
        for s in candidates
    ]
    sources.sort(key=lambda r: r.trust or 0.0, reverse=True)  # для trust-баров и порядка

    effects = [
        EffectRow(
            source_id=e.source_id,
            effect_type=e.effect_type,
            point=e.point,
            ci=_ci(e),
            variance_source=e.variance_source,
            evidence_span=e.evidence_span or "",
        )
        for e in state.get("extractions", [])
    ]

    queries = state.get("queries") or []
    translation = queries[0].translation if queries else None
    meta = state.get("meta")
    meta = meta if isinstance(meta, MetaResult) else None

    # Sensitivity-варианты пула (plan §8): leave-one-out + пере-пул без high-RoB.
    loo_rows = [
        LOORow(
            excluded_source_id=r.excluded_source_id,
            pooled_point=r.pooled_point,
            pooled_ci_low=r.pooled_ci_low,
            pooled_ci_high=r.pooled_ci_high,
            k_studies=r.k_studies,
        )
        for r in state.get("leave_one_out", [])
    ]
    sens_high_rob = state.get("sens_high_rob")
    sens_view: SensitivityView | None = None
    if meta is not None:
        if isinstance(sens_high_rob, MetaResult):
            sens_view = SensitivityView(
                leave_one_out=loo_rows,
                high_rob_pooled_point=sens_high_rob.pooled_point,
                high_rob_pooled_ci_low=sens_high_rob.pooled_ci_low,
                high_rob_pooled_ci_high=sens_high_rob.pooled_ci_high,
                high_rob_k_studies=sens_high_rob.k_studies,
                high_rob_note=(
                    "Пул совпадает с основным (нет high-RoB)"
                    if sens_high_rob.k_studies == meta.k_studies
                    else f"Пере-пул без high-RoB (k={sens_high_rob.k_studies})"
                ),
            )
        elif isinstance(sens_high_rob, Infeasible):
            sens_view = SensitivityView(
                leave_one_out=loo_rows,
                high_rob_note=f"Мета невозможна без high-RoB: {sens_high_rob.reason}",
            )
        else:
            sens_view = SensitivityView(leave_one_out=loo_rows)

    return ViewModel(
        hypothesis=state.get("raw_hypothesis", ""),
        pico=state.get("pico"),
        query_translation=translation,
        scoping=state.get("scoping"),
        sources=sources,
        effects=effects,
        prisma=state.get("prisma"),
        meta=meta,
        forest_path=meta.forest_plot_path if meta else None,
        funnel_path=meta.funnel_plot_path if meta else None,
        sensitivity=sens_view,
        report=state.get("report"),
    )
