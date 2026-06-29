"""Scimago SJR — квартиль журнала из офлайн-CSV (plan §6.1).

Без сети: таблица journal→quartile грузится из CSV в репозитории. Сопоставление
по нормализованному названию журнала.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


def _norm(journal: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", journal.lower())


@dataclass
class ScimagoTable:
    """Карта нормализованное_название_журнала → квартиль (Q1..Q4)."""

    by_journal: dict[str, str]

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        delimiter: str = ";",
        title_col: str = "Title",
        quartile_col: str = "SJR Best Quartile",
    ) -> ScimagoTable:
        table: dict[str, str] = {}
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter=delimiter):
                title = row.get(title_col)
                quartile = (row.get(quartile_col) or "").strip()
                if title and quartile in {"Q1", "Q2", "Q3", "Q4"}:
                    table[_norm(title)] = quartile
        return cls(by_journal=table)

    def quartile(self, journal: str | None) -> str | None:
        if not journal:
            return None
        return self.by_journal.get(_norm(journal))
