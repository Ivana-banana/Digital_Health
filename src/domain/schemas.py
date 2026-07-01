"""Доменные схемы (plan §4).

Чистые типы данных пайплайна. Без I/O, без сети, без LLM. Ключевой контракт —
`Extraction` с честной семантикой `unavailable`: LLM обязан вернуть «не сообщено»,
а не угадать число (plan §0.2, §9).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Синонимы мер эффекта от LLM → канонические коды (устойчивость извлечения, §0.2).
_EFFECT_SYNONYMS = {
    "hr": "HR",
    "hazard ratio": "HR",
    "or": "OR",
    "odds ratio": "OR",
    "rr": "RR",
    "risk ratio": "RR",
    "relative risk": "RR",
    "md": "MD",
    "mean difference": "MD",
    "smd": "SMD",
    "standardized mean difference": "SMD",
    "standardised mean difference": "SMD",
}

# --- Перечисления ---------------------------------------------------------


class StudyDesign(str, Enum):
    """Дизайн исследования — основа для trust-скоринга и выбора шкалы качества."""

    RCT = "rct"
    NON_RANDOMIZED = "non_randomized"
    OBSERVATIONAL = "observational"
    REVIEW = "review"
    META_ANALYSIS = "meta_analysis"
    CASE_REPORT = "case_report"
    OTHER = "other"
    UNKNOWN = "unknown"


# Меры эффекта, которые умеет пулить мета-анализ (plan §8).
EffectType = Literal["HR", "OR", "RR", "MD", "SMD"]

# Откуда восстановлена дисперсия эффекта (plan §0.2 — несущий контракт извлечения).
VarianceSource = Literal[
    "reported_ci",
    "reported_se",
    "derived_2x2",
    "derived_p",
    "unavailable",
]

# Источник текста, из которого извлечён эффект.
TextSource = Literal["abstract", "full_text"]

# Тип утверждения в provenance-сторе (факт vs интерпретация, plan §9).
ClaimType = Literal["fact", "interpretation"]

# Фиксированный enum причин исключения для PRISMA (plan §6.3).
ScreenReason = Literal[
    "wrong_population",
    "wrong_intervention",
    "wrong_outcome",
    "wrong_study_type",
    "not_english",
    "retracted",
    "duplicate",
    "no_extractable_data",
]

# Уровень доказательности по GRADE (plan §8).
GradeLevel = Literal["high", "moderate", "low", "very_low"]


# --- Структурирование вопроса --------------------------------------------


class PICO(BaseModel):
    """Структурированная гипотеза врача (Population/Intervention/Comparison/Outcome)."""

    population: str | None = None
    intervention: str | None = None
    comparison: str | None = None
    outcome: str | None = None

    def is_complete(self) -> bool:
        """Все четыре грани заполнены — можно строить поисковый запрос без уточнения."""
        return all([self.population, self.intervention, self.comparison, self.outcome])


class Query(BaseModel):
    """Поисковый запрос к источнику (EN). `translation` — QueryTranslation от ESearch."""

    source: str  # "pubmed" | "europepmc" | "openalex"
    raw: str
    translation: str | None = None


# --- Источники и идентичность --------------------------------------------


class Source(BaseModel):
    """Публикация-кандидат. ID-поля питают резолюцию дублей (`domain/identity`)."""

    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    # Trial-level ID (ClinicalTrials.gov) + акроним трайла — питают `collapse_by_trial`:
    # схлопнуть множество публикаций одного РКИ до одной первичной OS-публикации (plan §6.2).
    nct_id: str | None = None
    trial_acronym: str | None = None
    title: str = ""
    journal: str | None = None
    year: int | None = None
    abstract: str | None = None
    publication_types: list[str] = Field(default_factory=list)
    design: StudyDesign = StudyDesign.UNKNOWN
    citations: int | None = None
    sjr_quartile: str | None = None  # Q1..Q4
    retracted: bool = False
    trust_score: float | None = None


# --- Scoping (этап-1, plan §3) -------------------------------------------


class ScopingSummary(BaseModel):
    """Артефакт обзора поля: сколько публикаций, какие типы/исходы/популяции, пробелы."""

    total_candidates: int = 0
    by_design: dict[str, int] = Field(default_factory=dict)
    outcomes: list[str] = Field(default_factory=list)
    populations: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


# --- Систематический обзор (этап-2) --------------------------------------


class ScreenDecision(BaseModel):
    """Решение скринера по одному источнику → причина из фиксированного enum (PRISMA)."""

    source_id: str
    include: bool
    reason: ScreenReason | None = None  # причина исключения (если include=False)


class QueryTerms(BaseModel):
    """LLM-расширение PICO в фокусные поисковые термины PubMed (recall РКИ, plan §6.1).

    Грани соединяются как `(p OR ...) AND (i OR ...) AND (o OR ...)`. Для intervention —
    конкретные генерики обоих плеч (абстракты называют препараты, не классы).
    """

    population_terms: list[str] = Field(default_factory=list)
    intervention_terms: list[str] = Field(default_factory=list)
    outcome_terms: list[str] = Field(default_factory=list)


class ScreenJudgment(BaseModel):
    """LLM-вердикт семантического скрининга по PICO (вход → ScreenDecision).

    Дефолт `eligible=True`: при сбое/пустом ответе LLM не теряем исследование
    (recall важнее precision — лучше лишний кандидат, чем потерянный пивотный РКИ).
    """

    eligible: bool = True
    reason: Literal[
        "ok", "wrong_population", "wrong_intervention", "wrong_outcome", "wrong_study_type"
    ] = "ok"


class PrismaCounts(BaseModel):
    """Счётчики диаграммы PRISMA (включения/исключения по причинам)."""

    identified: int = 0
    after_dedup: int = 0
    screened: int = 0
    excluded: int = 0
    included: int = 0
    excluded_by_reason: dict[str, int] = Field(default_factory=dict)


class Extraction(BaseModel):
    """Извлечённый эффект. Контракт Extractor↔мета-gate: вместо догадки — `unavailable`.

    `effect_conversions` (stats/, P2) восстанавливает дисперсию там, где это возможно;
    `variance_source` фиксирует, откуда она взялась.
    """

    source_id: str = ""  # проставляется узлом извлечения; LLM его не знает
    design: StudyDesign = StudyDesign.UNKNOWN
    effect_type: EffectType | None = None
    point: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    se: float | None = None
    n_arm1: int | None = None
    n_arm2: int | None = None
    events1: int | None = None
    events2: int | None = None
    outcome: str = ""
    comparison: str = ""
    variance_source: VarianceSource = "unavailable"
    extraction_confidence: float = 0.0
    evidence_span: str = ""  # дословная цитата-обоснование
    text_source: TextSource = "abstract"

    @field_validator("effect_type", mode="before")
    @classmethod
    def _normalize_effect_type(cls, v: object) -> object:
        """Привести формулировку меры от LLM к коду (HR/OR/RR/MD/SMD)."""
        if v is None:
            return None
        return _EFFECT_SYNONYMS.get(str(v).strip().lower().replace("_", " "), v)


class Appraisal(BaseModel):
    """Критическая оценка качества (RoB 2.0 / ROBINS-I / STROBE по доменам, plan §8)."""

    source_id: str
    tool: str = ""  # "rob2" | "robins_i" | "strobe"
    domain_judgements: dict[str, str] = Field(default_factory=dict)
    overall: str = "unknown"  # low | some_concerns | high | unknown


# --- Мета-анализ ----------------------------------------------------------


class MetaResult(BaseModel):
    """Результат пулинга (plan §8): оценка, ДИ, гетерогенность, GRADE."""

    effect_type: EffectType
    outcome: str
    k_studies: int
    pooled_point: float
    pooled_ci_low: float
    pooled_ci_high: float
    model: str = "random_hksj"  # fixed | random_dl | random_hksj
    i_squared: float | None = None
    q_stat: float | None = None
    tau_squared: float | None = None
    egger_p: float | None = None
    grade: GradeLevel = "low"
    forest_plot_path: str | None = None
    funnel_plot_path: str | None = None


class Infeasible(BaseModel):
    """Структурное «почему мета-анализ невозможен» + чего не хватает (plan §8)."""

    reason: str
    missing: list[str] = Field(default_factory=list)


# --- Ответ и провенанс ----------------------------------------------------


class Claim(BaseModel):
    """Утверждение в provenance-сторе: факт vs интерпретация, со ссылкой и спаном."""

    text: str
    type: ClaimType
    source_id: str | None = None
    span: str | None = None
    verified: bool = False


class Report(BaseModel):
    """Финальный отчёт: градуированная доказательность, не бинарный вердикт (plan §9)."""

    summary: str = ""
    direction: str | None = None  # "favors_intervention" | "favors_control" | "no_effect"
    strength: str | None = None
    confidence: GradeLevel | None = None
    facts: list[Claim] = Field(default_factory=list)
    interpretations: list[Claim] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    disclaimer: str = "Не является клинической рекомендацией; решение — за врачом."


class Event(BaseModel):
    """Запись аудита/наблюдаемости одного узла (латентность, токены, статус)."""

    node: str
    status: str = "ok"  # ok | skipped | error
    detail: str | None = None
