"""Реранкер bge (plan §6.4): ранжирование пассажей, без torch в CI (fake CrossEncoder)."""

from __future__ import annotations

import asyncio

from src.adapters.rerank.bge_reranker import BGEReranker


class _FakeCrossEncoder:
    """predict возвращает скор = длина пассажа → длиннейший пассаж наверх."""

    def predict(self, pairs):
        return [float(len(p)) for _, p in pairs]


def _reranker() -> BGEReranker:
    r = BGEReranker()
    r._model = _FakeCrossEncoder()
    return r


def test_rerank_orders_by_score_desc_and_top_n():
    r = _reranker()
    order = asyncio.run(r.rerank("q", ["a", "abcd", "ab"], top_n=2))
    assert order == [1, 2]  # 'abcd'(4) > 'ab'(2) > 'a'(1); top_n=2


def test_rerank_empty_passages():
    r = _reranker()
    assert asyncio.run(r.rerank("q", [], top_n=3)) == []


def test_rerank_is_lazy():
    assert BGEReranker()._model is None
