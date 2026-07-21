"""neighbors.expand_with_neighbors — 오프라인 (fake supabase).

계약: hit 청크 text 가 같은 문서 ±radius 이웃의 idx 순 결합으로 교체되고,
경계(idx 0)·타 문서 비오염·실패 fail-open 이 지켜진다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compass_engine.neighbors import expand_with_neighbors  # noqa: E402
from compass_engine.stages import RetrievedChunk  # noqa: E402

# docA: idx 0..5, docB: idx 0..1
_ROWS = [
    {"id": f"A{i}", "document_id": "docA", "chunk_idx": i, "text": f"A{i}-본문"}
    for i in range(6)
] + [
    {"id": f"B{i}", "document_id": "docB", "chunk_idx": i, "text": f"B{i}-본문"}
    for i in range(2)
]


class _Q:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []

    def select(self, _cols):
        return self

    def eq(self, col, val):
        self._filters.append(lambda r: str(r.get(col)) == str(val))
        return self

    def in_(self, col, vals):
        vs = {str(v) for v in vals}
        self._filters.append(lambda r: str(r.get(col)) in vs)
        return self

    def execute(self):
        out = [r for r in self._rows if all(f(r) for f in self._filters)]
        return type("R", (), {"data": out})()


class FakeSB:
    def table(self, name):
        assert name == "nexus_chunks"
        return _Q(list(_ROWS))


class BoomSB:
    def table(self, *_a, **_k):
        raise RuntimeError("boom")


def _hit(cid: str, text: str = "원본") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, section_id="", document_id="", source_type="rule",
        breadcrumb="문서>제1조", article_no="제1조", text=text, score=1.0,
    )


def test_window_merge_ordered():
    out = expand_with_neighbors(FakeSB(), [_hit("A3")], radius=2)
    assert out[0]["text"] == "A1-본문\nA2-본문\nA3-본문\nA4-본문\nA5-본문"


def test_boundary_at_zero_and_no_cross_doc():
    out = expand_with_neighbors(FakeSB(), [_hit("B0")], radius=2)
    # docB 는 idx 0,1 뿐 — 음수 idx 없음, docA 텍스트 미혼입
    assert out[0]["text"] == "B0-본문\nB1-본문"
    assert "A" not in out[0]["text"]


def test_fail_open_returns_originals():
    hits = [_hit("A3", text="원본유지")]
    out = expand_with_neighbors(BoomSB(), hits, radius=2)
    assert out[0]["text"] == "원본유지"


def test_radius_zero_noop():
    hits = [_hit("A3", text="그대로")]
    assert expand_with_neighbors(FakeSB(), hits, radius=0)[0]["text"] == "그대로"
