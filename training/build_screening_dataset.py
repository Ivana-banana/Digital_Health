"""Сборка РЕАЛЬНОГО датасета для модели C (скрининг) из CLEF eHealth TAR 2019.

CLEF-TAR — открытый бенчмарк скрининга систематических обзоров (van de Schoot / Kanoulas
et al.). Task2 Intervention Training: 20 обзоров, ~31k документов с РУЧНОЙ разметкой
include/exclude на уровне title+abstract (qrels). Метки — от авторов Cochrane-обзоров.

Строим пары `query [SEP] doc`: query = клинический вопрос обзора (Title темы),
doc = title + abstract (тянем из PubMed по PMID). Позитивов мало (~1.4%) — берём все,
негативы сэмплируем на топик (recall(include) от сабсэмплинга негативов не зависит).

Выход: `training/screening_labels.csv` (query,doc,label) — читает train_models.py.
Запуск: `.venv/Scripts/python.exe training/build_screening_dataset.py`
"""

from __future__ import annotations

import csv
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters.search.pubmed import parse_efetch_xml  # noqa: E402

RAW = "https://raw.githubusercontent.com/CLEF-TAR/tar/master/2019-TAR/Task2/Training/Intervention/"
QRELS = RAW + "qrels/full.train.int.abs.2019.qrels"
TOPIC = RAW.replace("Task2", "Task1") + "topics/{}"  # Title лежит в Task1-темах
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

NEG_PER_POS = 3  # негативов на позитив (на топик); держим фетч и дисбаланс умеренными
BATCH = 120
MIN_ABSTRACT = 150
SEED = 0


def _sleep() -> None:
    time.sleep(0.4)  # без NCBI-ключа лимит 3 rps


def load_qrels(client: httpx.Client) -> dict[str, dict[str, int]]:
    text = client.get(QRELS, timeout=30, follow_redirects=True).text
    per: dict[str, dict[str, int]] = defaultdict(dict)
    for ln in text.splitlines():
        p = ln.split()
        if len(p) >= 4:
            per[p[0]][p[2]] = int(p[3])
    return per


def load_title(client: httpx.Client, topic: str) -> str:
    text = client.get(TOPIC.format(topic), timeout=20, follow_redirects=True).text
    for ln in text.splitlines():
        if ln.strip().startswith("Title:"):
            return ln.split("Title:", 1)[1].strip()
    return topic


def select_pmids(per: dict[str, dict[str, int]], rng: random.Random) -> dict[str, tuple[str, int]]:
    """PMID -> (topic, label): все позитивы + NEG_PER_POS негативов на топик."""
    chosen: dict[str, tuple[str, int]] = {}
    for topic, judgments in per.items():
        pos = [pmid for pmid, lab in judgments.items() if lab == 1]
        neg = [pmid for pmid, lab in judgments.items() if lab == 0]
        rng.shuffle(neg)
        for pmid in pos:
            chosen[pmid] = (topic, 1)
        for pmid in neg[: max(len(pos) * NEG_PER_POS, 10)]:
            chosen[pmid] = (topic, 0)
    return chosen


def fetch_docs(client: httpx.Client, pmids: list[str]) -> dict[str, str]:
    """PMID -> 'title. abstract' для записей с достаточным абстрактом."""
    docs: dict[str, str] = {}
    for i in range(0, len(pmids), BATCH):
        chunk = pmids[i : i + BATCH]
        r = client.post(EFETCH, data={"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"})
        for src in parse_efetch_xml(r.text):
            if src.pmid and src.abstract and len(src.abstract) >= MIN_ABSTRACT:
                text = f"{src.title}. {src.abstract}".replace("\n", " ").strip()
                docs[src.pmid] = text
        _sleep()
        print(f"  fetched {min(i + BATCH, len(pmids))}/{len(pmids)}")
    return docs


def main() -> None:
    rng = random.Random(SEED)
    with httpx.Client(timeout=30.0) as client:
        per = load_qrels(client)
        print(f"тем: {len(per)}")
        titles = {t: load_title(client, t) for t in per}
        _sleep()
        chosen = select_pmids(per, rng)
        print(f"выбрано PMID: {len(chosen)} (все позитивы + {NEG_PER_POS}× негативов/топик)")
        docs = fetch_docs(client, list(chosen))

    rows: list[tuple[str, str, str]] = []
    for pmid, (topic, label) in chosen.items():
        if pmid in docs:
            rows.append((titles[topic], docs[pmid], "include" if label else "exclude"))
    pos = sum(1 for r in rows if r[2] == "include")
    print(f"строк с абстрактом: {len(rows)} (include={pos}, exclude={len(rows) - pos})")

    out_path = Path(__file__).resolve().parent / "screening_labels.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query", "doc", "label"])
        w.writerows(rows)
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
