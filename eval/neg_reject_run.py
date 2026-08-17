"""지시서 010-r1 게이트 (c) — negative 6문항 거절 회귀 (합성 포함 미니 러닝).

운영 경로 직배선(retriever + synthesize + verify) — v1 사이드카 미경유
(v1_sidecar.py 의 NEXUS_CHAT_MODEL=3.6 setdefault 오염 회피, 004 교훈).
합성 모델 = 운영 기본값(synthesis._DEFAULT_CHAT_MODEL = gemini-3.7-flash).

기준선(사전 고정): ab37 A런(채택 구성, 2026-08-16) negative_marker_pass 5/6
(g51 만 완곡 거절 문면 — "규정되어 있지 않아 확인 필요" — 으로 엄격 마커
미포함, action=pass). 판정: 마커 pass ≥ 5/6 이고 미포함 문항도 거절 취지
문면이면 회귀 없음.

산출: eval/results/neg_reject_<ts>.json (무편집)
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

from compass_engine.anchors import build_anchor_map  # noqa: E402
from compass_engine.doc_router import DocRouter  # noqa: E402
from compass_engine.registry import load_ledger  # noqa: E402
from compass_engine.reranker import GeminiReranker  # noqa: E402
from compass_engine.synthesis import synthesize  # noqa: E402
from compass_engine.v1_retriever import (V1RpcRetriever,  # noqa: E402
                                         gemini_embed_fn)
from compass_engine.verify import verify_answer  # noqa: E402
from eval.runner import RESULTS_DIR, load_fixtures  # noqa: E402

_OOS_MARKERS = ("사규에서 확인되지 않", "확인되지 않는", "확인할 수 없")
BASELINE = {"run": "ab37_A_20260816T161550", "marker_pass": 5, "n": 6}


def main() -> int:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    ledger = load_ledger(sb)
    anchor_map = build_anchor_map(ledger)
    retr = V1RpcRetriever(sb, gemini_embed_fn(), top_k=5,
                          rpc_name="nexus_hybrid_search_v4_ctx",
                          expand_neighbors=True, neighbor_radius=1,
                          reranker=GeminiReranker(), rerank_pool=25,
                          router=DocRouter(sb), reserved_seats=2,
                          proxy_quota=1, chunk_cap=8)
    entries = [e for e in load_fixtures(_ROOT / "eval" / "golden.yaml")
               if e.get("category") == "negative"]
    records = []
    for e in entries:
        q = e["question"]
        rec: dict = {"id": e["id"], "question": q}
        try:
            res = retr.retrieve({"masked_text": q, "is_critical": False,
                                 "critical_matches": [], "oos": False,
                                 "faq_hit_id": None, "ambiguity": None},
                                {"tracks": ["rule"], "intent": "neg_reject"})
            syn = synthesize(q, res["chunks"], anchor_map=anchor_map)
            verdict = verify_answer(syn.answer_md, ledger,
                                    synthesis_integrity_ok=syn.integrity_ok)
            rec.update({
                "rerank_skipped": res["rank_trace"].get("rerank_skipped"),
                "router_hit": res.get("router_hit"),
                "n_chunks": len(res["chunks"]),
                "marker_pass": any(m in syn.answer_md for m in _OOS_MARKERS),
                "grade": verdict["grade"], "action": verdict["action"],
                "answer": syn.answer_md,
            })
        except Exception as ex:   # 결측 정직 표기
            rec["error"] = f"{type(ex).__name__}: {ex}"[:300]
        records.append(rec)
        print(json.dumps({k: v for k, v in rec.items() if k != "answer"},
                         ensure_ascii=False), flush=True)
        time.sleep(0.3)

    ok = [r for r in records if "error" not in r]
    n_pass = sum(1 for r in ok if r["marker_pass"])
    out = {"timestamp": datetime.now().isoformat(),
           "baseline": BASELINE,
           "aggregates": {
               "marker_pass": {"pass": n_pass, "n": len(records)},
               "rerank_skipped": {r["id"]: r.get("rerank_skipped") for r in ok},
               "errors": [r["id"] for r in records if "error" in r],
               "regression": n_pass < BASELINE["marker_pass"],
           },
           "records": records}
    path = RESULTS_DIR / f"neg_reject_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("\n== 게이트 (c) 판정 재료 ==")
    print(json.dumps(out["aggregates"], ensure_ascii=False, indent=1))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
