# Обучение в Yandex Cloud (обязательное требование, plan §7)

Засчитывается любой обученный компонент. Все три модели подключены в пайплайн за портами
(`ClassifierPort`/`ScreeningPort`/`RerankerPort`) и деградируют, если чекпойнта нет.

**Где запускать:** Yandex Cloud → **DataSphere** → community → project → загрузить ноутбук →
Run All (минуты на CPU). **Чекпойнты:** Object Storage → положить в `data/models/` (пути,
которые читает `src/app/live.py`). Метрики — на **human-checked gold**, не на авто-метках
(крит. 9).

## Ноутбуки

- `design_clf_min.ipynb` — **модель A** (классификатор дизайна). e5-small + LR-голова →
  `design_clf.joblib` → `data/models/design_clf.joblib`. Заполняет `design` там, где
  Publication Type молчит. Инференс: `src/adapters/classify/design_clf.py`. Метка — значение
  `StudyDesign` (`rct`/`observational`/`review`/`case_report`). Метрика: per-class F1 (цель 0.7–0.8).

- `screening_clf.ipynb` — **модель C** (скрининг include/exclude). e5-small (пара
  `PICO [SEP] title. abstract`) + LR с `predict_proba` → `screening_clf.joblib` →
  `data/models/screening_clf.joblib`. Инференс: `src/adapters/screen/biencoder_clf.py`
  (recall-first порог). Метрика: **recall(include) ≥ 0.95** (не терять РКИ).

- `reranker_ft.ipynb` — **модель B** (реранкер). `BAAI/bge-reranker-v2-m3` cross-encoder;
  инференс: `src/adapters/rerank/bge_reranker.py`. Адаптер грузит HF-модель напрямую —
  чекпойнт не обязателен; ноутбук считает **nDCG@10** и даёт опциональный fine-tune.

## Зависимости

`pip install -r requirements-ml.txt` (sentence-transformers, scikit-learn, joblib). Отдельно
от основного `requirements.txt` — judge/CI-образ их не тянет; адаптеры импортируют лениво.
