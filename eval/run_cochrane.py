"""Live Cochrane-бенчмарк (plan §10) — воспроизводимая сверка живого пула с gold-Cochrane.

Гоняет полный live-пайплайн (реальные PubMed + AI Studio из `.env`) на gold-PICO и печатает
report card «пул vs Cochrane + recall по included_pmids». Killer-аргумент питча + регресс-детектор
в ходе итераций A/D/B. Не подменяет frozen-eval — тот на замороженном корпусе для CI;
этот — live для питча (сеть+ключи обязательны).

Exit: 0 — pool_proximity ok И recall ≥ 2/3; 1 — метрики провалились; 2 — нет `.env` (skip).
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
from src.domain.schemas import MetaResult
from src.stats.meta import poolable

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "eval" / "gold"
DEFAULT_CASE = "cochrane_case_01"


def _load_gold(case_id: str) -> dict:
    path = GOLD_DIR / f"{case_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _pmid_from_source_id(sid: str) -> str | None:
    return sid[len("pmid:") :] if sid.startswith("pmid:") else None


def _sid_to_pmid_map(final: dict) -> dict[str, str]:
    return {identity_key(s): s.pmid for s in final.get("candidates", []) if s.pmid}


def _pmids_from_source_ids(sids: set[str], id_to_pmid: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for sid in sids:
        pmid = _pmid_from_source_id(sid) or id_to_pmid.get(sid)
        if pmid:
            out.add(pmid)
    return out


def _funnel_pmids(final: dict) -> tuple[set[str], set[str], set[str], set[str]]:
    """PMID-ы на каждом этапе воронки: candidates, screen-include, extract, pool."""
    id_to_pmid = _sid_to_pmid_map(final)
    candidate_pmids = {s.pmid for s in final.get("candidates", []) if s.pmid}
    include_sids = {d.source_id for d in final.get("screening", []) if d.include}
    include_pmids = _pmids_from_source_ids(include_sids, id_to_pmid)
    extract_sids = {e.source_id for e in final.get("extractions", [])}
    extract_pmids = _pmids_from_source_ids(extract_sids, id_to_pmid)
    pool_sids = {e.source_id for e in poolable(final.get("extractions", []))}
    pool_pmids = _pmids_from_source_ids(pool_sids, id_to_pmid)
    return candidate_pmids, include_pmids, extract_pmids, pool_pmids


def _funnel_ncts(final: dict) -> tuple[set[str], set[str], set[str], set[str]]:
    """NCT-ы на каждом этапе (trial-level recall — правильная метрика для воспроизведения Cochrane).

    Разные публикации одного РКИ имеют один NCT — trial-collapse может выбрать любую, пул всё равно
    представляет тот же трайл.
    """
    sid_to_nct = {identity_key(s): s.nct_id for s in final.get("candidates", []) if s.nct_id}
    candidate_ncts = {n for n in sid_to_nct.values() if n}
    include_sids = {d.source_id for d in final.get("screening", []) if d.include}
    include_ncts = {sid_to_nct[s] for s in include_sids if s in sid_to_nct}
    extract_sids = {e.source_id for e in final.get("extractions", [])}
    extract_ncts = {sid_to_nct[s] for s in extract_sids if s in sid_to_nct}
    pool_sids = {e.source_id for e in poolable(final.get("extractions", []))}
    pool_ncts = {sid_to_nct[s] for s in pool_sids if s in sid_to_nct}
    return candidate_ncts, include_ncts, extract_ncts, pool_ncts


def _cis_overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> bool:
    return not (a_high < b_low or b_high < a_low)


def _checks(final: dict, gold: dict) -> list[tuple[str, bool, str]]:
    """Report card: воронка recall gold-трайлов (NCT) + расхождение пула с Cochrane.

    Trial-level recall: Cochrane выбирает свои PMID редакторски, но метрика воспроизведения — это
    покрытие ТРАЙЛОВ (NCT), а не точных цитат. Разные публикации одного РКИ = тот же трайл.
    """
    gt = gold["ground_truth"]
    gold_ncts = set(gold["included_ncts"])
    n_gold = len(gold_ncts)

    meta = final.get("meta")
    is_meta = isinstance(meta, MetaResult)
    pool_point = meta.pooled_point if is_meta else None
    pool_lo = meta.pooled_ci_low if is_meta else None
    pool_hi = meta.pooled_ci_high if is_meta else None
    k = meta.k_studies if is_meta else None

    cands, incl, extr, pool = _funnel_ncts(final)
    hits_cand = cands & gold_ncts
    hits_incl = incl & gold_ncts
    hits_extr = extr & gold_ncts
    hits_pool = pool & gold_ncts

    proximity_ok = bool(
        is_meta
        and pool_point is not None
        and abs(pool_point - gt["pooled_point"]) <= 0.10
        and _cis_overlap(pool_lo, pool_hi, gt["pooled_ci_low"], gt["pooled_ci_high"])
    )
    recall_pool_ok = len(hits_pool) / n_gold >= 2 / 3

    pool_str = f"HR {pool_point:.2f} ({pool_lo:.2f}–{pool_hi:.2f}), k={k}" if is_meta else "no meta"
    cochrane_str = f"{gt['pooled_point']} ({gt['pooled_ci_low']}–{gt['pooled_ci_high']})"
    grade_str = meta.grade if is_meta else "—"

    def _funnel(hits: set[str]) -> str:
        return f"{len(hits)}/{n_gold} — {sorted(hits) or '∅'}"

    return [
        ("retrieve: gold трайлы (NCT) в кандидатах", True, _funnel(hits_cand)),
        ("screen: gold трайлы прошли скрининг", True, _funnel(hits_incl)),
        ("extract: gold трайлы в извлечении", True, _funnel(hits_extr)),
        (
            f"pool: trial-recall ≥ 2/3 (gold={sorted(gold_ncts)})",
            recall_pool_ok,
            _funnel(hits_pool),
        ),
        (f"пул близок к Cochrane {cochrane_str}", proximity_ok, pool_str),
        ("информативно: k_studies vs Cochrane 4", True, f"k={k}"),
        (
            f"информативно: GRADE vs Cochrane {gt['evidence_grade']}",
            True,
            f"наш GRADE={grade_str}",
        ),
    ]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Требуется живой доступ: без ключей — skip, не fail (CI без сети не должен ломаться).
    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("YANDEX_API_KEY") or not os.environ.get("YANDEX_FOLDER_ID"):
        print(
            "Live Cochrane-бенчмарк: требуется .env "
            "(YANDEX_API_KEY + YANDEX_FOLDER_ID) — пропускаем."
        )
        return 2

    case_id = DEFAULT_CASE
    for arg in sys.argv[1:]:
        if arg.startswith("--case="):
            case_id = arg[len("--case=") :]
    gold = _load_gold(case_id)
    hypothesis = gold["demo_hypothesis"]
    print(f"Live Cochrane-бенчмарк [{gold['case_id']}]: {gold['ground_truth']['comparison_label']}")
    print(f"Гипотеза: {hypothesis}")

    deps = build_live_deps(interactive=False, fulltext=bool(gold.get("requires_fulltext")))
    final = asyncio.run(run_full(hypothesis, deps))

    # Диагностика NCT-парсинга: если 0% кандидатов имеют NCT — парсер сломан (регресс).
    candidates = final.get("candidates", [])
    with_nct = sum(1 for s in candidates if s.nct_id)
    print(f"NCT parsed: {with_nct}/{len(candidates)} candidates")
    queries = final.get("queries") or []
    if queries:
        print(f"Query raw: {queries[0].raw[:200]}")
        print(f"QueryTranslation: {(queries[0].translation or '')[:200]}")

    checks = _checks(final, gold)
    for name, ok, detail in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name} — {detail}")
    passed = all(ok for _, ok, _ in checks)
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
