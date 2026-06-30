"""PII-скраб входа и анти-инъекция документов (plan §9) — чистые функции.

Узел 0 скрабит гипотезу врача (мед-данные конфиденциальны). Извлечённый контент
(абстракты) оборачивается делимитерами и трактуется LLM как данные, не инструкции.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")  # ≥10 знаков с разделителями — телефон
_LONG_ID = re.compile(r"\b\d{7,}\b")  # длинные числовые ID (номер карты/МКБ)

DOC_OPEN = "<<<DOCUMENT>>>"
DOC_CLOSE = "<<<END DOCUMENT>>>"


def scrub_pii(text: str) -> str:
    """Замаскировать e-mail, телефоны и длинные числовые идентификаторы."""
    text = _EMAIL.sub(REDACTED, text)
    text = _PHONE.sub(REDACTED, text)
    return _LONG_ID.sub(REDACTED, text)


def as_untrusted(text: str) -> str:
    """Обернуть текст документа делимитерами (контент = данные, не инструкции, §9)."""
    return f"{DOC_OPEN}\n{text}\n{DOC_CLOSE}"
