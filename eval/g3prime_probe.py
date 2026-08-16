"""지시서 009 G3′ — 승격 문서 오염 관측 (발효 전 1회 결박, 읽기 전용).

무관 질문 7건(g10, g47~g52)에 대해:
- 문항별 **최종 context_docs** 기록 (운영 구성 retriever.retrieve — 부기 러너
  요건 충족: 본 전용 러너가 context_docs 를 직접 기록하므로 ab37 선보강 불요)
- 승격 문서 2건(임직원 징계기준·CREDO)의 **리랭크 후 순위** 기록
  (proxy_pool_probe 확장 — RPC RRF 순위 + 동일 리랭커(pool 25) 재정렬 순위)

판정 규칙(사전 고정): 7건 전건에서 승격 문서 top_k(최종 컨텍스트) 진입 0건
→ 관측 통과. 1건 이상 진입 → 랭킹 보정 별도 안건 상정(발효 보류 사유 보고).

명문 개정 1줄: G3′의 "발효 전 1회 결박"은 "게이트=발효 비선결" 원칙의
의장 개정 채택분이다.

산출: eval/results/g3prime_<ts>.json (무편집)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from supabase import create_client  # noqa: E402

from compass_engine.doc_router import DocRouter  # noqa: E402
from compass_engine.reranker import GeminiReranker  # noqa: E402
from compass_engine.v1_retriever import (V1RpcRetriever,  # noqa: E402
                                         gemini_embed_fn)
from eval.runner import RESULTS_DIR, load_fixtures  # noqa: E402

PROMOTED = ("(공통) 임직원 징계기준", "(공통) 신세계그룹 CREDO")
IDS = ["g10", "g47", "g48", "g49", "g50", "g51", "g52"]
RERANK_POOL = 25


def main() -> int:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    embed = gemini_embed_fn()
    rr = GeminiReranker()
    retr = V1RpcRetriever(sb, embed, top_k=5,
                          rpc_name="nexus_hybrid_search_v4_ctx",
                          expand_neighbors=True, neighbor_radius=1,
                          reranker=GeminiReranker(), rerank_pool=RERANK_POOL,
                          router=DocRouter(sb), reserved_seats=2,
                          proxy_quota=1, chunk_cap=8)
    entries = {e["id"]: e for e in load_fixtures(_ROOT / "eval" / "golden.yaml")}
    out = {"timestamp": datetime.now().isoformat(),
           "promoted_docs": list(PROMOTED), "rerank_pool": RERANK_POOL,
           "records": []}
    for qid in IDS:
        q = entries[qid]["question"]
        # ① RPC top50 + 리랭크 후 순위 (proxy_pool_probe 확장)
        vec = embed(q)
        rows = sb.rpc("nexus_hybrid_search_v4_ctx",
                      {"query_embedding": vec, "query_text": q,
                       "match_count": 50, "pool_size": 300}).execute().data or []
        from compass_engine.stages import RetrievedChunk
        from compass_engine.articles import parse_article_ref
        pool = []
        for r in rows[:RERANK_POOL]:
            title = str(r.get("doc_title") or "")
            ref = parse_article_ref(str(r.get("article_no") or ""))
            canon = ref.canonical if ref else None
            pool.append(RetrievedChunk(
                chunk_id=str(r.get("id") or ""), section_id="",
                document_id=str(r.get("document_id") or ""), source_type="rule",
                breadcrumb=f"{title}>{canon}" if canon else title,
                article_no=canon, text=str(r.get("text") or ""),
                score=float(r.get("rrf_score") or 0.0)))
        ranked = rr(q, pool)
        rrf_ranks = {d: [i + 1 for i, r in enumerate(rows)
                         if str(r.get("doc_title") or "") == d] for d in PROMOTED}
        rerank_ranks = {d: [i + 1 for i, c in enumerate(ranked)
                            if c["breadcrumb"].split(">")[0] == d]
                        for d in PROMOTED}
        # ② 운영 구성 최종 컨텍스트 (top_k+예약석+이웃+cap)
        res = retr.retrieve({"masked_text": q, "is_critical": False,
                             "critical_matches": [], "oos": False,
                             "faq_hit_id": None, "ambiguity": None},
                            {"tracks": ["rule"], "intent": "g3prime"})
        ctx_docs = sorted({c["breadcrumb"].split(">")[0] for c in res["chunks"]})
        entered = [d for d in PROMOTED if d in ctx_docs]
        rec = {"id": qid, "question": q,
               "rrf_top50_ranks": rrf_ranks,
               "rerank_ranks_pool25": rerank_ranks,
               "final_context_docs": ctx_docs,
               "router_hit": res.get("router_hit"),
               "promoted_in_topk": entered}
        out["records"].append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        time.sleep(0.3)
    entered_any = [r["id"] for r in out["records"] if r["promoted_in_topk"]]
    out["verdict"] = {
        "rule": "7건 전건 top_k(최종 컨텍스트) 진입 0 → 통과",
        "entered": entered_any,
        "pass": not entered_any,
    }
    print("G3' verdict:", json.dumps(out["verdict"], ensure_ascii=False))
    path = RESULTS_DIR / f"g3prime_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
