"""Live-сводка по всем gold-кейсам — питчевый слайд «воспроизвели N обзоров из M».

Прогоняет последовательно всё в `eval/gold/*.json` (кроме отложенных) через live-пайплайн
и печатает markdown-таблицу «кейс | Cochrane | наш пул | recall | GRADE | статус». Экспорт
в `eval/artifacts/live_summary.json` для будущих слайдов/README.

Exit: 0 — все кейсы PASS; 1 — хотя бы один FAIL; 2 — нет `.env` (skip).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from src.app.live import build_live_deps
from src.app.main import run_full
from src.domain.identity import identity_key
from src.domain.schemas import Infeasible, MetaResult
from src.stats.meta import poolable

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "eval" / "gold"
ARTIFACTS = ROOT / "eval" / "artifacts"

# Список кейсов для сводки — по порядку презентации на питче.
# Отложенный `cochrane_case_02_trastuzumab` не включаем (требует full-text mining).
CASES: list[str] = [
    "cochrane_case_01",  # BRAF+MEK меланома, OS
    "cochrane_case_03_pd1_nsclc",  # anti-PD-(L)1 NSCLC, OS
    "case_02_insufficient",  # sotorasib — insufficient
]


def _load_gold(case_id: str) -> dict:
    return json.loads((GOLD_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


def _cochrane_str(gold: dict) -> str:
    gt = gold.get("ground_truth")
    if not gt:
        return "—"
    return (
        f"HR {gt['pooled_point']} ({gt['pooled_ci_low']}–{gt['pooled_ci_high']}), "
        f"k={gt['n_studies_cochrane']}, {gt['evidence_grade']}"
    )


def _pool_recall_grade(final: dict, gold: dict) -> tuple[str, str, str, str, bool]:
    """(pool_str, recall_str, grade_str, status_note, passed)."""
    meta = final.get("meta")
    if isinstance(meta, MetaResult):
        pool_str = (
            f"HR {meta.pooled_point:.2f} "
            f"({meta.pooled_ci_low:.2f}–{meta.pooled_ci_high:.2f}), k={meta.k_studies}"
        )
        grade = meta.grade
    else:
        pool_str = "Infeasible" if isinstance(meta, Infeasible) else "—"
        grade = "—"

    # Recall по NCT (для Cochrane-репро кейсов).
    gold_ncts = set(gold.get("included_ncts") or [])
    sid_to_nct = {identity_key(s): s.nct_id for s in final.get("candidates", []) if s.nct_id}
    pool_ncts = set()
    if isinstance(meta, MetaResult):
        for e in poolable(final.get("extractions", [])):
            nct = sid_to_nct.get(e.source_id)
            if nct:
                pool_ncts.add(nct)
    hits = pool_ncts & gold_ncts
    recall_str = f"{len(hits)}/{len(gold_ncts)}" if gold_ncts else "—"

    # PASS / FAIL логика по типу кейса.
    exp = gold.get("expected_report") or {}
    if exp.get("meta_feasible") is False:
        # Insufficient-кейс: meta НЕ должна быть feasible.
        passed = not isinstance(meta, MetaResult)
        status = "PASS: честный отказ" if passed else "FAIL: пул собрался (не ожидался)"
    elif gold.get("ground_truth"):
        # Cochrane-репро: точка пула близка и recall ≥ 2/3.
        gt = gold["ground_truth"]
        if isinstance(meta, MetaResult):
            close = abs(meta.pooled_point - gt["pooled_point"]) <= 0.10
            recall_ok = not gold_ncts or (len(hits) / len(gold_ncts) >= 2 / 3)
            passed = close and recall_ok
            status = "PASS" if passed else "FAIL"
        else:
            passed = False
            status = "FAIL: мета не собралась"
    else:
        passed = False
        status = "FAIL: неизвестный тип"
    return pool_str, recall_str, grade, status, passed


def _print_table(rows: list[dict]) -> None:
    """Markdown-таблица для питча — прямо в stdout."""
    print()
    print("| Кейс | Cochrane | Наш live | Recall | GRADE | Статус |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['case_id']} | {r['cochrane']} | {r['pool']} | {r['recall']} | "
            f"{r['grade']} | {r['status']} |"
        )


def _run_case(case_id: str) -> dict:
    print(f"\n=== {case_id} ===", flush=True)
    gold = _load_gold(case_id)
    hypothesis = gold["demo_hypothesis"]
    deps = build_live_deps(interactive=False)
    try:
        final = asyncio.run(run_full(hypothesis, deps))
    except Exception as exc:
        return {
            "case_id": case_id,
            "cochrane": _cochrane_str(gold),
            "pool": f"ERROR: {type(exc).__name__}",
            "recall": "—",
            "grade": "—",
            "status": "FAIL: exception",
            "passed": False,
        }
    pool_str, recall_str, grade, status, passed = _pool_recall_grade(final, gold)
    print(f"  → {pool_str} | recall {recall_str} | GRADE {grade} | {status}", flush=True)
    return {
        "case_id": case_id,
        "cochrane": _cochrane_str(gold),
        "pool": pool_str,
        "recall": recall_str,
        "grade": grade,
        "status": status,
        "passed": passed,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("YANDEX_API_KEY") or not os.environ.get("YANDEX_FOLDER_ID"):
        print("Live-сводка: требуется .env (YANDEX_API_KEY + YANDEX_FOLDER_ID) — пропускаем.")
        return 2

    print(f"Live-сводка по {len(CASES)} gold-кейсам (питчевый слайд)")
    rows = [_run_case(cid) for cid in CASES]
    _print_table(rows)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / "live_summary.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON-сводка сохранена: {out}")

    passed = sum(1 for r in rows if r["passed"])
    print(f"\nИтог: {passed}/{len(rows)} кейсов PASS")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
