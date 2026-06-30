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
    MetaResult,
    PrismaCounts,
    Report,
    ScopingSummary,
    Source,
)


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
    """Строка таблицы эффектов: честная семантика variance_source (plan §0.2)."""

    source_id: str
    effect_type: str | None
    point: float | None
    ci: str  # "0.44–0.77" либо "" если не сообщён
    variance_source: str


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
        )
        for e in state.get("extractions", [])
    ]

    queries = state.get("queries") or []
    translation = queries[0].translation if queries else None
    meta = state.get("meta")
    meta = meta if isinstance(meta, MetaResult) else None

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
        report=state.get("report"),
    )
