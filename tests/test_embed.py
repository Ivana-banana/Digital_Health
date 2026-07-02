"""bge-m3-обёртка (plan §6.4): ленивая загрузка + приведение векторов, без torch в CI.

Модель инжектится fake-объектом (`_model`) → проверяем glue `embed` (форма/float),
не таща sentence-transformers. `DenseEmbedder`-контракт `embed` совместим с `hybrid_retrieve`.
"""

from __future__ import annotations

from src.adapters.embed.bge_m3 import BGEM3Embedder


class _FakeST:
    def encode(self, texts, normalize_embeddings=True):
        return [[len(t), 0] for t in texts]


def test_embed_is_lazy_until_called():
    emb = BGEM3Embedder()
    assert emb._model is None  # sentence-transformers не импортируется при конструировании


def test_embed_converts_to_float_lists():
    emb = BGEM3Embedder()
    emb._model = _FakeST()
    out = emb.embed(["ab", "abcd"])
    assert out == [[2.0, 0.0], [4.0, 0.0]]
    assert all(isinstance(x, float) for row in out for x in row)
