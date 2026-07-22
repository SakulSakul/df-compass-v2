"""v2 정본 파이프라인 골든 러닝 — retrieve(v4-ctx+rerank+neighbors) →
섹션 계약 합성(3.6 확정) → 인용 스코어러. 동결 베이스라인 대비 Δ 판정용.
env: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, GEMINI_API_KEY"""
from __future__ import annotations
import json, os, re, sys, time
from datetime import datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from supabase import create_client
from compass_engine.citations import check_citations, summarize_checks
from compass_engine.registry import load_ledger
from compass_engine.reranker import GeminiReranker
from compass_engine.synthesis import synthesize
from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn
from eval.runner import RESULTS_DIR, load_fixtures
from eval.rerank_ab import _pct
from eval.golden_ab import _score  # 채점 로직 재사용 (doc-level=제목 출현)

url = os.environ["SUPABASE_URL"]
ledger = load_ledger(create_client(url, os.environ["SUPABASE_SERVICE_KEY"]))
rr = GeminiReranker()
retr = V1RpcRetriever(create_client(url, os.environ["SUPABASE_ANON_KEY"]),
                      gemini_embed_fn(), top_k=3,
                      rpc_name="nexus_hybrid_search_v4_ctx",
                      expand_neighbors=True, reranker=rr)
entries = load_fixtures(_ROOT / "eval" / "golden.yaml")
records, agg = [], {"tok_na": 0, "exp_hit": 0, "exp_total": 0, "fab": 0,
                    "neg_pass": 0, "neg_total": 0, "contract_ng": 0,
                    "fallback": 0, "elapsed": []}
failed_ids = []
for i, e in enumerate(entries, 1):
    q = e["question"]
    # 일시 네트워크 오류 내성 — 1회 재시도 후에도 실패면 기록하고 계속
    # (단건 ConnectError 가 52문항 러닝 전체를 무효화하지 않도록)
    for attempt in (1, 2):
        try:
            res = retr.retrieve({"masked_text": q, "is_critical": False,
                                 "critical_matches": [], "oos": False,
                                 "faq_hit_id": None, "ambiguity": None},
                                {"tracks": ["rule"], "intent": "pipeline"})
            syn = synthesize(q, res["chunks"])
            break
        except Exception as ex:
            print(f"[pipeline] {e['id']} attempt{attempt} FAILED: "
                  f"{type(ex).__name__}: {ex}", file=sys.stderr, flush=True)
            if attempt == 2:
                syn = None
            else:
                time.sleep(5)
    if syn is None:
        failed_ids.append(e["id"])
        continue
    sc = _score(syn.answer_md, e, ledger)
    agg["exp_hit"] += sc["expected_hit"]; agg["exp_total"] += sc["expected_total"]
    agg["fab"] += 1 if sc["has_fabrication"] else 0
    if "negative_pass" in sc:
        agg["neg_total"] += 1; agg["neg_pass"] += 1 if sc["negative_pass"] else 0
    agg["contract_ng"] += 0 if syn.section_contract_ok else 1
    agg["fallback"] += 1 if syn.used_fallback else 0
    agg["elapsed"].append(syn.elapsed_ms)
    records.append({"id": e["id"], "category": e.get("category"), "question": q,
                    "answer": syn.answer_md, "provider": syn.provider,
                    "section_contract_ok": syn.section_contract_ok,
                    "elapsed_ms": syn.elapsed_ms, "score": sc})
    print(f"… {i}/{len(entries)}", flush=True)
path = RESULTS_DIR / f"pipeline_golden_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
path.write_text(json.dumps({"timestamp": datetime.now().isoformat(),
                            "pipeline": "v4-ctx+rerank+neighbors → synthesis(3.6)",
                            "records": records}, ensure_ascii=False, indent=2),
                encoding="utf-8")
er = agg["exp_hit"] / agg["exp_total"]
print("\n════ v2 정본 파이프라인 · golden 52 ════")
print(f"기대 인용 재현율 {agg['exp_hit']}/{agg['exp_total']} ({er:.1%})")
print(f"위조 인용 답변  {agg['fab']}/52")
print(f"negative pass   {agg['neg_pass']}/{agg['neg_total']}")
print(f"섹션 계약 위반  {agg['contract_ng']}/52  |  fallback 사용 {agg['fallback']}")
print(f"합성 지연 p50 {_pct(agg['elapsed'], .5):.0f}ms  p95 {_pct(agg['elapsed'], .95):.0f}ms")
print(f"rerank 실패 {rr.failures}  |  문항 실패 {len(failed_ids)}: {failed_ids}")
print(f"Wrote {path}")
