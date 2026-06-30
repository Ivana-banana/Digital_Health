"""Frozen-eval-subset (plan §10) — детерминированный quality-gate для CI и питча.

Прогоняет пайплайн на замороженном корпусе (без сети/ключей) и проверяет хард-гейты:
hallucinated-reference rate = 0 (каждый факт отчёта верифицирован), мета-анализ
воспроизводится (k=2, пул HR в ожидаемом коридоре), PRISMA отсекает ретракцию.
Печатает сводку метрик; exit 0 при прохождении, 1 при провале. Не подменяет pytest —
это отдельный воспроизводимый прогон «как на демо» (== единый корпус, plan §10, §12).
"""

from __future__ import annotations

import asyncio
import sys

from src.app.main import DEMO_HYPOTHESIS, build_demo_deps, run_full
from src.domain.schemas import MetaResult


def _checks(final) -> list[tuple[str, bool, str]]:
    report = final.get("report")
    meta = final.get("meta")
    prisma = final.get("prisma")
    facts = report.facts if report else []
    no_hallu = bool(facts) and all(c.verified for c in facts)
    is_meta = isinstance(meta, MetaResult)
    pooled = meta.pooled_point if is_meta else None
    k = meta.k_studies if is_meta else None
    meta_ok = bool(is_meta and k == 2 and pooled and 0.55 < pooled < 0.66)
    retr = prisma.excluded_by_reason.get("retracted") if prisma else None
    prisma_ok = bool(prisma and prisma.included == 2 and retr == 1)
    return [
        ("отчёт сгенерирован", report is not None, repr(bool(report))),
        ("hallucinated-reference rate = 0", no_hallu, "0.00" if no_hallu else "1.00"),
        ("мета воспроизводится (k=2, пул HR≈0.61)", meta_ok, f"k={k}, pooled={pooled}"),
        ("PRISMA: включено 2, ретракция исключена", prisma_ok, f"retracted={retr}"),
    ]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    final = asyncio.run(run_full(DEMO_HYPOTHESIS, build_demo_deps()))
    checks = _checks(final)
    print("Frozen-eval (анти-PD-1 при меланоме, OS):")
    for name, ok, detail in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name} — {detail}")
    passed = all(ok for _, ok, _ in checks)
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
