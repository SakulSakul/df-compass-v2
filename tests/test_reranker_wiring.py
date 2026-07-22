"""V1RpcRetriever + reranker 주입 배선 — 오프라인 (fake supabase·fake reranker)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from compass_engine.v1_retriever import V1RpcRetriever


class _FakeSB:
    def __init__(self):
        self.last_payload = None
    def rpc(self, name, payload):
        self.last_payload = payload
        rows = [{"id": f"c{i}", "document_id": f"d{i}", "text": f"본문{i}",
                 "article_no": None, "doc_title": f"문서{i}", "rrf_score": 1.0 - i*0.01}
                for i in range(payload["match_count"])]
        return type("Q", (), {"execute": lambda s: type("R", (), {"data": rows})()})()


def _intake(q="질문"):
    return {"masked_text": q, "is_critical": False, "critical_matches": [],
            "oos": False, "faq_hit_id": None, "ambiguity": None}


def test_rerank_pool_expansion_and_cut():
    sb = _FakeSB()
    def reverse_rerank(q, chunks):
        return list(reversed(chunks))
    r = V1RpcRetriever(sb, lambda t: [0.0]*768, top_k=3,
                       expand_neighbors=False, reranker=reverse_rerank,
                       rerank_pool=15)
    out = r.retrieve(_intake(), {"tracks": ["rule"], "intent": "t"})
    assert sb.last_payload["match_count"] == 15          # pool 확장
    assert len(out["chunks"]) == 3                       # top_k 컷
    assert out["chunks"][0]["chunk_id"] == "c14"         # 재정렬 반영
    assert "+rerank" in out["provider"]


def test_no_reranker_keeps_topk_fetch():
    sb = _FakeSB()
    r = V1RpcRetriever(sb, lambda t: [0.0]*768, top_k=3, expand_neighbors=False)
    out = r.retrieve(_intake(), {"tracks": ["rule"], "intent": "t"})
    assert sb.last_payload["match_count"] == 3
    assert "+rerank" not in out["provider"]
