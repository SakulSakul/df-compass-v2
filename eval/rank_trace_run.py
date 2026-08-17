"""지시서 010 P1 — 골든 52 전수 3층 순위 실측 (운영 동일 경로, 읽기 전용).

운영 retrieve 경로 그대로(운영 RPC·쿼리 변환·intake 마스킹 포함) — retrieve()
내부 P1 계장(rank_trace)이 계기. 프로브식 별도 RPC 금지(계기 편향 —
keyword leg 사망 순위) 준수. 합성·verify 는 미실행(검색 계층 실측).

기록: 문항별 {최종 top_k(컨텍스트) 청크의 원 RRF 순위 분포, 승격 문서
(징계기준·CREDO) 3층 순위, 실반환 행수} + N 판정 재료 집계
(관련 질문 rescue 후보 / 무관 질문 승격 문서 운영 계기 RRF 분포).

산출: eval/results/rank_trace_<ts>.json (무편집)
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
from compass_engine.intake import run_intake  # noqa: E402
from compass_engine.reranker import GeminiReranker  # noqa: E402
from compass_engine.v1_retriever import (V1RpcRetriever,  # noqa: E402
                                         gemini_embed_fn)
from eval.runner import RESULTS_DIR, load_fixtures  # noqa: E402

PROMOTED = ("(공통) 임직원 징계기준", "(공통) 신세계그룹 CREDO")
N_PROVISIONAL = 10        # 잠정값 — 판정 재료 집계용 (확정은 감리자 회부 후)
IRRELEVANT = {"g10", "g47", "g48", "g49", "g50", "g51", "g52"}   # G3′ 그룹 계승


def main() -> int:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    retr = V1RpcRetriever(sb, gemini_embed_fn(), top_k=5,
                          rpc_name="nexus_hybrid_search_v4_ctx",
                          expand_neighbors=True, neighbor_radius=1,
                          reranker=GeminiReranker(), rerank_pool=25,
                          router=DocRouter(sb), reserved_seats=2,
                          proxy_quota=1, chunk_cap=8)
    entries = load_fixtures(_ROOT / "eval" / "golden.yaml")
    records = []
    for i, e in enumerate(entries, 1):
        q = e["question"]
        rec: dict = {"id": e["id"], "category": e.get("category"),
                     "irrelevant_group": e["id"] in IRRELEVANT}
        try:
            intake = run_intake(sb, q)
            res = retr.retrieve(intake, {"tracks": ["rule"], "intent": "p1"})
            rt = res["rank_trace"]
            promoted = {}
            for d in PROMOTED:
                rrf = [r for cid, r in rt["rrf_rank"].items()]
                # 문서별 3층: rrf/rerank 는 trace 의 chunk 단위 → 문서 매핑
                doc_chunks = [f for f in rt["final"] if f["doc"] == d]
                # 풀 단위 순위 (final 밖 포함) — rerank_rank 를 문서로 묶기
                # 위해 ranked 시점 breadcrumb 이 필요하나 trace 는 id 기반 —
                # final 밖 문서 순위는 rrf_rank 원시로 별도 산출 불가(관측
                # 전용 계장 원칙) → 문서별 final 진입 여부+진입 청크 순위 기록
                promoted[d] = {"in_final": bool(doc_chunks),
                               "final_chunks": doc_chunks}
            rec.update({
                "rpc_returned": rt["rpc_returned"],
                "final": rt["final"],
                "final_topk_rrf": [f["rrf"] for f in rt["final"]],
                "router_hit": res.get("router_hit"),
                "promoted": promoted,
            })
        except Exception as ex:   # 결측 정직 표기
            rec["error"] = f"{type(ex).__name__}: {ex}"[:200]
        records.append(rec)
        print(f"[{i}/{len(entries)}] {e['id']} "
              f"rrf_dist={rec.get('final_topk_rrf')} err={'error' in rec}",
              flush=True)
        time.sleep(0.2)

    ok = [r for r in records if "error" not in r]
    rel = [r for r in ok if not r["irrelevant_group"]]
    irr = [r for r in ok if r["irrelevant_group"]]
    # (i) 관련 질문 rescue 후보: 최종 진입 청크 중 원 RRF > N (이웃·주입 None 제외)
    rescue = []
    for r in rel:
        deep = [f for f in r["final"]
                if f["rrf"] is not None and f["rrf"] > N_PROVISIONAL]
        if deep:
            rescue.append({"id": r["id"],
                           "deep_entries": deep})
    # (ii) 무관 질문 승격 문서 진입·순위
    irr_promoted = [{"id": r["id"],
                     "promoted_in_final": {d: v["in_final"]
                                           for d, v in r["promoted"].items()},
                     "chunks": {d: v["final_chunks"]
                                for d, v in r["promoted"].items() if v["in_final"]}}
                    for r in irr]
    out = {"timestamp": datetime.now().isoformat(),
           "n_provisional": N_PROVISIONAL,
           "note": "운영 동일 경로(retrieve 내부 계장) — 프로브 편향 계기 아님",
           "aggregates": {
               "errors": [r["id"] for r in records if "error" in r],
               "rescue_candidates_rel_questions": rescue,
               "irrelevant_promoted_entries": irr_promoted,
           },
           "records": records}
    path = RESULTS_DIR / f"rank_trace_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("\n== N 판정 재료 ==")
    print("관련 질문 rescue 후보(RRF>10 최종 진입):",
          json.dumps(rescue, ensure_ascii=False))
    print("무관 그룹 승격 문서 진입:",
          json.dumps([x for x in irr_promoted
                      if any(x["promoted_in_final"].values())],
                     ensure_ascii=False))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
