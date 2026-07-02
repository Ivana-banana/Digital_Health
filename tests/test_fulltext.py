"""Чистое ядро full-text RAG (plan §6.4): чанкинг + BM25 + гибрид BM25×dense (RRF).

Все функции детерминированы и не требуют сети/эмбеддера — dense-путь проверяется
на fake-эмбеддере с заданными векторами. bge-m3 подключается за `DenseEmbedder` (A3).
"""

from __future__ import annotations

from src.domain.fulltext import (
    bm25_scores,
    chunk_fulltext,
    fuse_hybrid,
    hybrid_retrieve,
)

# Полный текст с секцией Results, где OS-HR — то, чего нет в абстракте (кейс трастузумаба).
_OS_PARA = (
    "At a median follow-up of 8 years, overall survival was significantly improved "
    "with trastuzumab; the hazard ratio for death was 0.66 (95% CI 0.57 to 0.77)."
)
_PFS_PARA = (
    "Disease-free survival at 3 years was 81% versus 74%; the hazard ratio was 0.64 "
    "for disease-free survival events."
)
_METHODS_PARA = (
    "Patients were randomly assigned in a 1:1 ratio to receive chemotherapy with or "
    "without trastuzumab. Randomization was stratified by nodal status and hormone receptors."
)


def test_chunk_fulltext_splits_and_bounds():
    text = "\n\n".join([_METHODS_PARA, _PFS_PARA, _OS_PARA] * 4)
    chunks = chunk_fulltext(text, max_chars=400)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)
    assert all(len(c) <= 400 + 200 for c in chunks)  # допускаем overlap-хвост


def test_chunk_fulltext_short_text_single_chunk():
    chunks = chunk_fulltext(_OS_PARA, max_chars=1200)
    assert len(chunks) == 1
    assert "hazard ratio for death was 0.66" in chunks[0]


def test_bm25_ranks_os_paragraph_top():
    chunks = [_METHODS_PARA, _PFS_PARA, _OS_PARA]
    scores = bm25_scores(chunks, ["overall", "survival", "death", "hazard", "ratio"])
    assert scores[2] == max(scores)  # OS-параграф — самый релевантный к OS-запросу


def test_bm25_empty_query_is_zero():
    scores = bm25_scores([_OS_PARA, _PFS_PARA], [])
    assert scores == [0.0, 0.0]


def test_fuse_hybrid_rrf_rewards_agreement():
    # doc0 высоко в обоих ранжированиях → должен победить после слияния.
    bm25 = [3.0, 1.0, 0.0]
    dense = [0.9, 0.2, 0.1]
    fused = fuse_hybrid(bm25, dense)
    assert len(fused) == 3
    assert fused[0] == max(fused)


def test_hybrid_retrieve_bm25_only_without_embedder():
    chunks = [_METHODS_PARA, _PFS_PARA, _OS_PARA]
    top = hybrid_retrieve(chunks, "overall survival hazard ratio for death", None, top_k=1)
    assert top == [_OS_PARA]


class _FakeEmbedder:
    """Детерминированный DenseEmbedder: вектор = [дот с ключевыми токенами]."""

    _KEYS = ("survival", "death", "trastuzumab", "disease-free")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(t.lower().count(k)) for k in self._KEYS] for t in texts]


def test_hybrid_retrieve_with_dense_embedder():
    chunks = [_METHODS_PARA, _PFS_PARA, _OS_PARA]
    top = hybrid_retrieve(chunks, "overall survival death", _FakeEmbedder(), top_k=2)
    assert _OS_PARA in top
    assert len(top) == 2
