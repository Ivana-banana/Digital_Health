"""Live-бенчмарк «доказательств недостаточно» (plan §15, второй демо-кейс).

Проверяет ЧЕСТНЫЙ отказ системы, когда данных мало: разреженная гипотеза → пайплайн
находит кандидатов, но пул невозможен (<2 сопоставимых) → report.strength='insufficient',
direction=None, meta=Infeasible. Комплемент к `run_cochrane.py` (репро) — вместе показывают:
система не гадает, честно сообщает границы доказательств.

Exit: 0 — все хард-гейты прошли; 1 — метрики провалились; 2 — нет `.env` (skip).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from src.app.live import build_live_deps
from src.app.main import run_full
from src.domain.schemas import Infeasible, MetaResult

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "case_02_insufficient.json"


def _load_gold() -> dict:
    return json.loads(GOLD.read_text(encoding="utf-8"))


def _checks(final: dict, gold: dict) -> list[tuple[str, bool, str]]:
    """Хард-гейты честного отказа: пайплайн работает, но пул невозможен → insufficient."""
    exp = gold["expected_report"]
    candidates = final.get("candidates", [])
    prisma = final.get("prisma")
    meta = final.get("meta")
    report = final.get("report")

    n_cands = len(candidates)
    included = prisma.included if prisma else 0
    is_meta = isinstance(meta, MetaResult)
    report_direction = report.direction if report else "n/a"
    report_strength = report.strength if report else "n/a"
    report_conf = report.confidence if report else "n/a"

    return [
        (
            f"пайплайн нашёл кандидатов ≥{exp['min_candidates']} (не пустая выдача)",
            n_cands >= exp["min_candidates"],
            f"{n_cands} кандидатов, {included} после скрининга",
        ),
        (
            "мета-анализ НЕвозможен (Infeasible / <2 сопоставимых)",
            not is_meta or (is_meta and meta.k_studies < 2),
            (
                f"Infeasible: {meta.reason}"
                if isinstance(meta, Infeasible)
                else (
                    f"meta feasible, k={meta.k_studies}"
                    if is_meta
                    else "meta=None (Infeasible-подобное)"
                )
            ),
        ),
        (
            "report.direction = null (нет бинарного вердикта)",
            report_direction is None,
            f"direction={report_direction!r}",
        ),
        (
            "report.strength = 'insufficient' (честный отказ)",
            report_strength == "insufficient",
            f"strength={report_strength!r}, confidence={report_conf!r}",
        ),
        (
            "нет галлюцинаций: все факты verified или их нет",
            not report or all(c.verified for c in report.facts) or not report.facts,
            f"facts={len(report.facts) if report else 0}",
        ),
    ]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("YANDEX_API_KEY") or not os.environ.get("YANDEX_FOLDER_ID"):
        print(
            "Live insufficient-бенчмарк: требуется .env "
            "(YANDEX_API_KEY + YANDEX_FOLDER_ID) — пропускаем."
        )
        return 2

    gold = _load_gold()
    hypothesis = gold["demo_hypothesis"]
    print(f"Live insufficient-бенчмарк [{gold['case_id']}]")
    print(f"Гипотеза: {hypothesis}")
    print(f"Ожидание: {gold['expected_report']['reason_note']}")

    deps = build_live_deps(interactive=False)
    final = asyncio.run(run_full(hypothesis, deps))

    candidates = final.get("candidates", [])
    print(f"NCT parsed: {sum(1 for s in candidates if s.nct_id)}/{len(candidates)} candidates")

    checks = _checks(final, gold)
    for name, ok, detail in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name} — {detail}")
    passed = all(ok for _, ok, _ in checks)
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
