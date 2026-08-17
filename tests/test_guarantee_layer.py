"""wave 3 보장 계층 — 오프라인 (fake sb·router·reranker).

고정하는 불변식: ① add-only (라우터 no-op 시 기존 흐름과 동일) ② 예약석
컷 면제 ③ 프록시 감점·쿼터 ≤1 ④ cap ⑤ router_hit 기록.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from compass_engine.v1_retriever import V1RpcRetriever

PROXY = "(공통) 신세계그룹 CREDO"
RULE_A = "(CSR) 대외출강 운영 지침"
RULE_B = "(재무) 법인카드 관리 지침"


def _row(i, title, doc):
    return {"id": f"c{i}", "document_id": doc, "doc_title": title,
            "article_no": None, "text": f"{title} 본문 {i}", "rrf_score": 1.0 - i * 0.01}


class _FakeSb:
    """rpc → 고정 풀. table(nexus_chunks) → 라우팅 문서 청크."""
    def __init__(self, pool_rows, doc_chunks=None):
        self._pool = pool_rows
        self._doc_chunks = doc_chunks or {}

    def rpc(self, name, payload):
        rows = self._pool
        class _R:  # noqa: N801
            data = rows
            def execute(self): return self
        return _R()

    def table(self, name):
        dc = self._doc_chunks
        class _T:  # noqa: N801
            def __init__(self): self._doc = None
            def select(self, *a): return self
            def eq(self, col, val): self._doc = val; return self
            def in_(self, *a): return self
            def execute(self):
                class _R:  # noqa: N801
                    data = [dict(r, document_id=self._doc) if False else r
                            for r in dc.get(self._doc, [])]
                r = _R(); r.data = dc.get(self._doc, []); return r
        return _T()


class _FakeRouter:
    def __init__(self, titles, confident=True, title_to_id=None):
        self._titles = titles
        self._confident = confident
        self.title_to_id = title_to_id or {}
    def route(self, q):
        return {"doc_titles": self._titles, "confident": self._confident}


def _retr(sb, **kw):
    kw.setdefault("expand_neighbors", False)
    kw.setdefault("reranker", None)
    return V1RpcRetriever(sb, lambda t: [0.0] * 768,
                          rpc_name="x", **kw)


_INTAKE = {"masked_text": "질의", "is_critical": False, "critical_matches": [],
           "oos": False, "faq_hit_id": None, "ambiguity": None}
_ROUTE = {"tracks": ["rule"], "intent": "test"}


def test_no_router_baseline_unchanged():
    sb = _FakeSb([_row(i, RULE_A, "dA") for i in range(6)])
    res = _retr(sb, top_k=3).retrieve(_INTAKE, _ROUTE)
    assert len(res["chunks"]) == 3 and res["router_hit"] is None


def test_router_low_confidence_is_noop():
    sb = _FakeSb([_row(i, RULE_A, "dA") for i in range(6)])
    router = _FakeRouter([RULE_B], confident=False, title_to_id={RULE_B: "dB"})
    res = _retr(sb, top_k=3, router=router).retrieve(_INTAKE, _ROUTE)
    assert len(res["chunks"]) == 3 and res["router_hit"] is None
    assert all(c["document_id"] == "dA" for c in res["chunks"])


def test_reserved_seat_injects_and_exempts_cut():
    # 풀에 라우팅 문서(dB)가 없음 → 주입 + 예약석으로 최종 포함 (컷 면제)
    sb = _FakeSb([_row(i, RULE_A, "dA") for i in range(6)],
                 doc_chunks={"dB": [{"id": "b1", "document_id": "dB",
                                     "text": "질의 관련 본문"}]})
    router = _FakeRouter([RULE_B], title_to_id={RULE_B: "dB"})
    res = _retr(sb, top_k=3, router=router, reserved_seats=2,
                proxy_quota=1, chunk_cap=8).retrieve(_INTAKE, _ROUTE)
    docs = [c["document_id"] for c in res["chunks"]]
    assert "dB" in docs                    # 컷 면제 — top_k 밖이어도 포함
    assert res["router_hit"] is True
    assert len(res["chunks"]) <= 8


def test_proxy_demotion_and_quota(monkeypatch):
    # 풀 상위가 프록시 도배 → 감점으로 비프록시 우선, 최종 프록시 ≤1
    # (009 이후 운영 명단 공집합 — 합성 명단 주입으로 기제 검증 유지.
    # retriever._is_proxy 는 호출 시점 import 라 proxies 모듈 패치가 유효)
    import compass_engine.proxies as _px
    monkeypatch.setattr(_px, "PROXY_DOCS", frozenset({PROXY}))
    rows = ([_row(i, PROXY, "dP") for i in range(3)]
            + [_row(10 + i, RULE_A, "dA") for i in range(3)])
    sb = _FakeSb(rows)
    res = _retr(sb, top_k=4, proxy_quota=1).retrieve(_INTAKE, _ROUTE)
    titles = [c["breadcrumb"].split(">")[0] for c in res["chunks"]]
    assert titles.count(PROXY) <= 1
    assert titles[0] == RULE_A             # 감점 — 비프록시가 앞


def test_chunk_cap():
    sb = _FakeSb([_row(i, RULE_A, f"d{i}") for i in range(12)])
    res = _retr(sb, top_k=10, chunk_cap=8).retrieve(_INTAKE, _ROUTE)
    assert len(res["chunks"]) == 8


def _rev_reranker(q, chunks):
    """순서 검증용 fake — 호출되면 역순 반환 (스킵/수행 구분 계기)."""
    return list(reversed(chunks))


def test_p2prime_no_designation_skips_rerank():
    # P2′ (010-r1): 라우터 무지목(저확신) → 리랭크 스킵, RRF 순서 그대로
    sb = _FakeSb([_row(i, RULE_A, "dA") for i in range(6)])
    router = _FakeRouter([RULE_B], confident=False, title_to_id={RULE_B: "dB"})
    res = _retr(sb, top_k=3, router=router,
                reranker=_rev_reranker).retrieve(_INTAKE, _ROUTE)
    assert res["rank_trace"]["rerank_skipped"] is True
    assert [c["chunk_id"] for c in res["chunks"]] == ["c0", "c1", "c2"]  # RRF 순서


def test_p2prime_designation_keeps_rerank():
    # P2′ (010-r1): 확신 지목 → 현행 리랭크 유지 (역순 fake 반영 확인)
    sb = _FakeSb([_row(i, RULE_A, "dA") for i in range(6)])
    router = _FakeRouter([RULE_A], confident=True, title_to_id={RULE_A: "dA"})
    res = _retr(sb, top_k=3, router=router,
                reranker=_rev_reranker).retrieve(_INTAKE, _ROUTE)
    assert res["rank_trace"]["rerank_skipped"] is False
    assert [c["chunk_id"] for c in res["chunks"]] == ["c5", "c4", "c3"]  # 리랭크 적용


def test_p2prime_no_router_baseline_rerank_unchanged():
    # P2′ (010-r1): 라우터 미구성 → 스킵 없음 (기존 동작 보존)
    sb = _FakeSb([_row(i, RULE_A, "dA") for i in range(6)])
    res = _retr(sb, top_k=3, reranker=_rev_reranker).retrieve(_INTAKE, _ROUTE)
    assert res["rank_trace"]["rerank_skipped"] is False
    assert [c["chunk_id"] for c in res["chunks"]] == ["c5", "c4", "c3"]


def test_p2prime_skip_downstream_unchanged(monkeypatch):
    # P2′ (010-r1): 스킵 시에도 하류(프록시 감점·쿼터·cap) 불변 동작
    import compass_engine.proxies as _px
    monkeypatch.setattr(_px, "PROXY_DOCS", frozenset({PROXY}))
    rows = ([_row(i, PROXY, "dP") for i in range(3)]
            + [_row(10 + i, RULE_A, "dA") for i in range(3)]
            + [_row(20 + i, RULE_B, "dB") for i in range(6)])
    sb = _FakeSb(rows)
    router = _FakeRouter([], confident=False)
    res = _retr(sb, top_k=4, router=router, reranker=_rev_reranker,
                proxy_quota=1, chunk_cap=8).retrieve(_INTAKE, _ROUTE)
    assert res["rank_trace"]["rerank_skipped"] is True
    titles = [c["breadcrumb"].split(">")[0] for c in res["chunks"]]
    assert titles.count(PROXY) <= 1        # 쿼터
    assert titles[0] == RULE_A             # 감점 — 비프록시가 앞 (RRF 순서 유지)
    assert len(res["chunks"]) <= 8         # cap


def test_rank_trace_instrumentation():
    # P1 계장 (010): 관측 전용 — 반환 청크 무영향 + 3층 기록 구조 실재
    rows = [_row(i, RULE_A, f"d{i}") for i in range(6)]
    sb = _FakeSb(rows)
    res = _retr(sb, top_k=3).retrieve(_INTAKE, _ROUTE)
    rt = res["rank_trace"]
    assert rt["rpc_returned"] == 6
    assert set(rt["rrf_rank"].values()) == {1, 2, 3, 4, 5, 6}
    assert rt["rerank_rank"]                       # 리랭크 층 기록
    assert len(rt["final"]) == len(res["chunks"])  # 최종층 = 반환 청크 1:1
    assert all("rrf" in f and "rerank" in f for f in rt["final"])
