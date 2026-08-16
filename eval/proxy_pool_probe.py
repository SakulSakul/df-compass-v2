"""지시서 007 — P0 프로브: 징계기준 청크의 하이브리드 top50·리랭크 풀 진입 실측.

읽기 전용(운영 코드 무변경). 5문항 각각 하이브리드 RPC top50 결과와 리랭크
입력 풀(운영 구성 rerank_pool=25 — 실측 파라미터 값을 JSON 에 기재)에서
"(공통) 임직원 징계기준" 청크의 유무·순위·id 원시 기록.

주의(008 관계): 008 승격이 선완료된 상태에서 실행 — 본 프로브는 "검색 진입
여부" 관측으로 그대로 유효(풀 미진입이면 승격·감점 완화 무관하게 노출 불가).

산출: eval/results/proxy_probe_<ts>.json
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

from compass_engine.v1_retriever import gemini_embed_fn  # noqa: E402
from eval.runner import RESULTS_DIR  # noqa: E402

PENALTY = "(공통) 임직원 징계기준"
RPC = "nexus_hybrid_search_v4_ctx"
TOPN = 50
RERANK_POOL = 25          # 운영 구성 (app.py·compare 하니스 rerank_pool=25)

QS = [
    ("Q1", "법인카드를 개인 용도로 사용해도 되나요?"),
    ("Q2", "회사 비품을 집에 가져가면 어떻게 되나요?"),
    ("Q3", "경비를 허위로 청구하면 어떻게 되나요?"),
    ("Q4", "회사 공금을 개인 용도로 쓴 경우 징계 수위는 어떻게 되나요?"),   # g14 양성 대조
    ("Q5", "국내 출장 시 숙박비 한도가 궁금합니다."),                      # g01 계열 음성 대조
]


def main() -> int:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    embed = gemini_embed_fn()
    out = {"timestamp": datetime.now().isoformat(), "rpc": RPC,
           "top_n": TOPN, "rerank_pool_param": RERANK_POOL,
           "note_008": "008 승격 선완료 상태 — 검색 진입 여부 관측",
           "records": []}
    for qid, q in QS:
        vec = embed(q)
        rows = sb.rpc(RPC, {"query_embedding": vec, "query_text": q,
                            "match_count": TOPN,
                            "pool_size": max(30, TOPN * 6)}).execute().data or []
        hits = [(i + 1, r) for i, r in enumerate(rows)
                if str(r.get("doc_title") or "") == PENALTY]
        rec = {
            "id": qid, "question": q,
            "top50_total": len(rows),
            "penalty_chunks_in_top50": len(hits),
            "best_rank": hits[0][0] if hits else None,
            "in_rerank_pool": bool(hits and hits[0][0] <= RERANK_POOL),
            "penalty_ranks": [rk for rk, _ in hits],
            "penalty_chunk_ids": [str(r.get("id")) for _, r in hits],
        }
        out["records"].append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        time.sleep(0.3)
    p0 = [r for r in out["records"] if r["id"] in ("Q1", "Q2", "Q3")]
    out["p0_verdict"] = {
        "rule": "Q1~Q3 중 1건 이상 리랭크 풀 진입 → P0 통과",
        "entered": [r["id"] for r in p0 if r["in_rerank_pool"]],
        "pass": any(r["in_rerank_pool"] for r in p0),
    }
    print("P0:", json.dumps(out["p0_verdict"], ensure_ascii=False))
    path = RESULTS_DIR / f"proxy_probe_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
