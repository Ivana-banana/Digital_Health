"""Сборка РЕАЛЬНОГО датасета для модели A (дизайн) из PubMed.

Метки — кураторские `PublicationType` от NLM (не синтетика): по одному запросу на класс,
label = запрошенный класс. Тянем только записи с абстрактом, дедуп по PMID, балансируем.
Выход: `training/design_labels.csv` (колонки text,label) — его читает train_models.py.

Запуск: `.venv/Scripts/python.exe training/build_design_dataset.py`
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters.search.pubmed import parse_efetch_xml, parse_esearch  # noqa: E402

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PER_CLASS = 250  # берём с запасом; после фильтра «есть абстракт» останется меньше
BATCH = 120  # размер efetch-порции
MIN_ABSTRACT = 200  # символов — режем куцые записи без текста дизайна

# Онко-контекст + язык/люди; NOT-исключения снижают перекрёстную загрязнённость меток.
_BASE = "neoplasms[mesh] AND hasabstract AND english[lang] AND humans[mesh]"
QUERIES: dict[str, str] = {
    "rct": f'"randomized controlled trial"[pt] AND {_BASE}',
    "review": (
        f'("systematic review"[pt] OR "meta-analysis"[pt] OR review[pt]) AND {_BASE} '
        'NOT "randomized controlled trial"[pt]'
    ),
    "case_report": (
        f'"case reports"[pt] AND {_BASE} NOT "randomized controlled trial"[pt] NOT review[pt]'
    ),
    "observational": (
        '("observational study"[pt] OR "cohort studies"[mesh] OR "case-control studies"[mesh]) '
        f"AND {_BASE} "
        'NOT "randomized controlled trial"[pt] NOT review[pt] NOT "case reports"[pt]'
    ),
}


def _sleep() -> None:
    time.sleep(0.4)  # без NCBI-ключа лимит 3 rps — держим дистанцию


def fetch_ids(client: httpx.Client, term: str, retmax: int) -> list[str]:
    r = client.get(
        ESEARCH,
        params={"db": "pubmed", "term": term, "retmax": str(retmax), "retmode": "json"},
    )
    ids, _ = parse_esearch(r.json())
    _sleep()
    return ids


def fetch_abstracts(client: httpx.Client, ids: list[str]) -> list[str]:
    # Формат текста совпадает с инференсом адаптера (design_clf.py): "title. abstract".
    out: list[str] = []
    for i in range(0, len(ids), BATCH):
        chunk = ids[i : i + BATCH]
        r = client.post(EFETCH, data={"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"})
        for src in parse_efetch_xml(r.text):
            if src.abstract and len(src.abstract) >= MIN_ABSTRACT:
                text = f"{src.title}. {src.abstract}".replace("\n", " ").strip()
                out.append(text)
        _sleep()
    return out


def main() -> None:
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    with httpx.Client(timeout=30.0) as client:
        for label, term in QUERIES.items():
            ids = fetch_ids(client, term, PER_CLASS)
            texts = fetch_abstracts(client, ids)
            kept = 0
            for t in texts:
                if t in seen:
                    continue
                seen.add(t)
                rows.append((t, label))
                kept += 1
            print(f"[{label}] ids={len(ids)} -> с абстрактом+уник={kept}")

    out_path = Path(__file__).resolve().parent / "design_labels.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["text", "label"])
        w.writerows(rows)
    print(f"\nВсего строк: {len(rows)} -> {out_path}")


if __name__ == "__main__":
    main()
