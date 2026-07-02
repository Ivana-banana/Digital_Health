"""Чистое ядро full-text RAG (plan §6.4).

Детерминированные функции без сети/ML: чанкинг полного текста, лексический BM25
и гибридное слияние BM25×dense через Reciprocal Rank Fusion. Dense-сигнал приходит
за `DenseEmbedder` (bge-m3 в `adapters/embed`, A3) — при его отсутствии ретрив
деградирует до чистого BM25. Порядок и математика тестируются без эмбеддера.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol

_WORD_RE = re.compile(r"[a-z0-9]+")


class DenseEmbedder(Protocol):
    """Плотный энкодер текста → векторы (реализуется bge-m3-адаптером, plan §6.4)."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def chunk_fulltext(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Разбить полный текст на чанки по параграфам (<= max_chars) с overlap-хвостом.

    Параграфы (разделённые пустой строкой) группируются в тела до `max_chars`;
    слишком длинный параграф жёстко режется. Каждый чанк, кроме первого, получает
    префикс из последних `overlap` символов предыдущего тела (контекст на стыке).
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        if len(p) <= max_chars:
            pieces.append(p)
        else:
            pieces.extend(p[i : i + max_chars] for i in range(0, len(p), max_chars))

    bodies: list[str] = []
    cur = ""
    for pc in pieces:
        if cur and len(cur) + 1 + len(pc) > max_chars:
            bodies.append(cur)
            cur = pc
        else:
            cur = f"{cur} {pc}" if cur else pc
    if cur:
        bodies.append(cur)

    chunks: list[str] = []
    for i, body in enumerate(bodies):
        if i > 0 and overlap > 0:
            chunks.append(f"{bodies[i - 1][-overlap:]} {body}")
        else:
            chunks.append(body)
    return chunks


def bm25_scores(
    chunks: list[str], query_terms: list[str], *, k1: float = 1.5, b: float = 0.75
) -> list[float]:
    """Okapi BM25: релевантность каждого чанка запросу (чистый Python, plan §6.4)."""
    if not chunks or not query_terms:
        return [0.0] * len(chunks)
    q = [t.lower() for t in query_terms]
    docs = [_tokenize(c) for c in chunks]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n
    dfs = {term: sum(1 for d in docs if term in d) for term in set(q)}

    scores: list[float] = []
    for d in docs:
        tf = Counter(d)
        dl = len(d)
        s = 0.0
        for term in q:
            df = dfs.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            f = tf.get(term, 0)
            denom = f + k1 * (1 - b + b * dl / avgdl) if avgdl else f + k1
            if denom:
                s += idf * (f * (k1 + 1)) / denom
        scores.append(s)
    return scores


def _rank_positions(scores: list[float]) -> list[int]:
    """Позиция каждого индекса при сортировке по убыванию скора (0 — лучший)."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ranks = [0] * len(scores)
    for pos, idx in enumerate(order):
        ranks[idx] = pos
    return ranks


def fuse_hybrid(
    bm25: list[float], dense: list[float], *, method: str = "rrf", k: int = 60
) -> list[float]:
    """Слить BM25 и dense-скоры (разные шкалы) через Reciprocal Rank Fusion (plan §6.4)."""
    if method != "rrf":
        raise ValueError(f"unsupported fusion method: {method}")
    rb, rd = _rank_positions(bm25), _rank_positions(dense)
    return [1.0 / (k + rb[i]) + 1.0 / (k + rd[i]) for i in range(len(bm25))]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def hybrid_retrieve(
    chunks: list[str], query: str, embedder: DenseEmbedder | None, *, top_k: int
) -> list[str]:
    """Top-k чанков по гибриду BM25×dense; без эмбеддера — чистый BM25 (plan §6.4)."""
    if not chunks:
        return []
    bm25 = bm25_scores(chunks, _tokenize(query))
    if embedder is None:
        fused = bm25
    else:
        qv = embedder.embed([query])[0]
        dense = [_cosine(qv, cv) for cv in embedder.embed(chunks)]
        fused = fuse_hybrid(bm25, dense)
    order = sorted(range(len(chunks)), key=lambda i: fused[i], reverse=True)
    return [chunks[i] for i in order[:top_k]]
