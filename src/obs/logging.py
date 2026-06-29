"""Структурное JSON-логирование на узел (plan §10).

Один JSON-объект на событие (узел, статус, латентность, токены, стоимость) с общим
`run_id`. Стриминг этих событий — одновременно UX (крит. 8) и видимость E2E (крит. 1).
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TextIO


@dataclass
class StructuredLogger:
    """Пишет по одной JSON-строке на событие; `run_id` связывает события одного прогона."""

    name: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    stream: TextIO = field(default=sys.stderr)

    def event(self, node: str, status: str = "ok", **fields: Any) -> None:
        record = {
            "ts": round(time.time(), 3),
            "run_id": self.run_id,
            "logger": self.name,
            "node": node,
            "status": status,
            **fields,
        }
        self.stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.stream.flush()


def get_logger(name: str) -> StructuredLogger:
    """Фабрика логгера с новым `run_id`."""
    return StructuredLogger(name=name)
