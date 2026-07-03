"""Обучение моделей A (дизайн) и C (скрининг) — самодостаточный скрипт для запуска в YC.

Конвертация ноутбуков `design_clf_min.ipynb` + `screening_clf.ipynb` в один запускаемый `.py`,
чтобы обучать на Compute VM без DataSphere (см. `ya-cloud.md`, раздел «План Б»). Не зависит от
нашего репозитория — только `sentence-transformers`, `scikit-learn`, `joblib` (ставятся на VM).

Метки берутся из демо-сэмпла (формальный чекпойнт) ЛИБО из CSV, если положить рядом со скриптом:
  design_labels.csv     колонки: text,label      (label ∈ rct/observational/review/case_report)
  screening_labels.csv  колонки: query,doc,label  (label ∈ include/exclude)

Выход: `design_clf.joblib` и `screening_clf.joblib` в текущей папке → скачать в `data/models/`
(пути, которые читает `src/app/live.py`). Запуск: `python3 train_models.py`.
"""

import csv
from pathlib import Path

import joblib
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, recall_score
from sklearn.model_selection import train_test_split

ENCODER = "intfloat/multilingual-e5-small"  # тот же энкодер, что в адаптерах
SEP = " [SEP] "  # разделитель пары PICO/источник (совпадает с biencoder_clf.py)
SCREEN_THRESHOLD = 0.3  # низкий порог включения → recall-first (совпадает с адаптером)

# --- Демо-сэмплы (совпадают с ноутбуками). ЗАМЕНИТЬ на CSV для честных метрик жюри. ---
DESIGN_DEMO: list[tuple[str, str]] = [
    ("Randomized controlled trial comparing drug A vs placebo, double-blind.", "rct"),
    ("We randomly assigned 200 patients to two arms in a phase III trial.", "rct"),
    ("Retrospective cohort study of registry data over 10 years.", "observational"),
    ("A prospective observational cohort followed for survival outcomes.", "observational"),
    ("This systematic review and meta-analysis pooled 12 studies.", "review"),
    ("Narrative review of immunotherapy in melanoma.", "review"),
    ("Case report of a rare adverse event in one patient.", "case_report"),
    ("We describe a single case of unexpected response.", "case_report"),
]

SCREEN_DEMO: list[tuple[str, str, str]] = [
    (
        "melanoma BRAF+MEK vs BRAF overall survival",
        "Dabrafenib plus trametinib vs dabrafenib in melanoma. OS hazard ratio 0.71.",
        "include",
    ),
    (
        "melanoma BRAF+MEK vs BRAF overall survival",
        "Cost-effectiveness analysis of targeted therapy in melanoma.",
        "exclude",
    ),
    (
        "HER2+ breast cancer trastuzumab overall survival",
        "Adjuvant trastuzumab vs chemotherapy alone in HER2+ EBC. Survival improved.",
        "include",
    ),
    (
        "HER2+ breast cancer trastuzumab overall survival",
        "Review of cardiotoxicity monitoring guidelines.",
        "exclude",
    ),
]


def _load_design() -> list[tuple[str, str]]:
    path = Path("design_labels.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            rows = [(r["text"], r["label"]) for r in csv.DictReader(f)]
        print(f"[A] данные из {path} ({len(rows)} строк)")
        return rows
    print(f"[A] демо-сэмпл ({len(DESIGN_DEMO)} строк) — положи design_labels.csv для метрик")
    return DESIGN_DEMO


def _load_screen() -> list[tuple[str, str, str]]:
    path = Path("screening_labels.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            rows = [(r["query"], r["doc"], r["label"]) for r in csv.DictReader(f)]
        print(f"[C] данные из {path} ({len(rows)} строк)")
        return rows
    print(f"[C] демо-сэмпл ({len(SCREEN_DEMO)} строк) — положи screening_labels.csv для метрик")
    return SCREEN_DEMO


def train_design(encoder: SentenceTransformer) -> None:
    """Модель A: e5-small + LR-голова, метки = значения StudyDesign."""
    data = _load_design()
    texts = [t for t, _ in data]
    labels = [y for _, y in data]
    x = encoder.encode(texts, normalize_embeddings=True)
    try:  # честная метрика на hold-out, если хватает данных на stratified split
        x_tr, x_te, y_tr, y_te = train_test_split(
            x, labels, test_size=0.25, random_state=0, stratify=labels
        )
        holdout = LogisticRegression(max_iter=1000).fit(x_tr, y_tr)
        print(classification_report(y_te, holdout.predict(x_te)))
    except ValueError as exc:
        print(f"[A] hold-out пропущен ({exc}) — слишком мало данных на класс")
    clf = LogisticRegression(max_iter=1000).fit(x, labels)  # финальный — на всех данных
    joblib.dump(clf, "design_clf.joblib")
    print("[A] сохранён design_clf.joblib")


def train_screening(encoder: SentenceTransformer) -> None:
    """Модель C: пара `query [SEP] doc` через e5-small + LR, recall-first порог."""
    rows = _load_screen()
    texts = [q + SEP + doc for q, doc, _ in rows]
    labels = [y for _, _, y in rows]
    x = encoder.encode(texts, normalize_embeddings=True)
    clf = LogisticRegression(max_iter=1000).fit(x, labels)
    col = list(clf.classes_).index("include")
    proba = clf.predict_proba(x)[:, col]
    pred = ["include" if p >= SCREEN_THRESHOLD else "exclude" for p in proba]
    print("recall(include):", recall_score(labels, pred, pos_label="include"))
    print(classification_report(labels, pred))
    joblib.dump(clf, "screening_clf.joblib")
    print("[C] сохранён screening_clf.joblib")


def main() -> None:
    print(f"Загрузка энкодера {ENCODER} ...")
    encoder = SentenceTransformer(ENCODER)
    print("=== Модель A: классификатор дизайна ===")
    train_design(encoder)
    print("=== Модель C: скрининг include/exclude ===")
    train_screening(encoder)
    print("Готово. Файлы design_clf.joblib + screening_clf.joblib -> положить в data/models/")


if __name__ == "__main__":
    main()
