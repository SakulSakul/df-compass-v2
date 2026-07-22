"""3.6 Flash 선행 벤치 — 합성 모델 교체 없이 토큰·지연만 계측 (지시 2026-07-21).

현행(gemini-3.5-flash, v1 NEXUS_CHAT_MODEL 코드 기본값) vs gemini-3.6-flash.
- 비교 축: 출력 토큰 · TTFT(스트림 첫 청크) · 총 생성시간 — **품질 판정 아님**
  (품질은 Phase 1 인용 스코어러 완성 후 저장본 소급 채점 — 재실행 불요).
- 조건 통제: fixture 별 retrieval 1회(v4-ctx top3 + 이웃결합) → 동일 컨텍스트·
  동일 프롬프트를 양 모델에 투입. 양쪽 모두 기본 설정(thinking 미지정) —
  광고 문구("출력 17% 감소·지연 감소")를 기본값 기준으로 검증.
- 답변 전문 + 컨텍스트 + 계측치를 eval/results/synth_bench_*.json 에 저장.

env: SUPABASE_URL, SUPABASE_ANON_KEY, GEMINI_API_KEY
사용법: python eval/synth_bench.py [--top-k 3]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn  # noqa: E402
from eval.runner import DEFAULT_FIXTURES, RESULTS_DIR, load_fixtures  # noqa: E402
from eval.rerank_ab import _pct  # noqa: E402  (p50/p95 헬퍼 재사용)

MODEL_A = "gemini-3.5-flash"      # 현행 (v1 NEXUS_CHAT_MODEL 코드 기본값)
MODEL_B = "gemini-3.6-flash"

_PROMPT = """당신은 신세계디에프 사규 안내 챗봇입니다. 아래 [사규 발췌]만 근거로
질문에 답하세요. 근거 조항을 (문서명, 제N조) 형식으로 본문에 인용하고,
발췌에 없는 내용은 지어내지 말고 "확인 필요"로 표시하세요.

[질문]
{q}

[사규 발췌]
{ctx}"""


def _gen_stream(cli, model: str, prompt: str) -> dict:
    """스트리밍 1회 — TTFT·총시간·출력토큰·finish·전문.

    계측 이력(정직 기록): 1차(stream)·2차(non-stream) 모두 max_output_tokens
    =1024 에서 답변 절단 — 근본원인은 SSE 유실이 아니라 **기본 thinking 이
    출력 예산을 소모해 MAX_TOKENS 로 종료**(finish_reason 실측 11/16·10/16).
    → 상한 4096 + finish_reason 검증으로 확정. 완결성은 finish=STOP 으로 판정.
    """
    t0 = time.perf_counter()
    ttft_ms = None
    parts: list[str] = []
    out_tokens = None
    finish = None
    for ev in cli.models.generate_content_stream(
        model=model, contents=prompt,
        config={"temperature": 0.0, "max_output_tokens": 4096},
    ):
        txt = getattr(ev, "text", "") or ""
        if txt and ttft_ms is None:
            ttft_ms = (time.perf_counter() - t0) * 1000
        parts.append(txt)
        cand = (getattr(ev, "candidates", None) or [None])[0]
        if cand is not None and getattr(cand, "finish_reason", None):
            finish = str(cand.finish_reason)
        um = getattr(ev, "usage_metadata", None)
        if um is not None and getattr(um, "candidates_token_count", None):
            out_tokens = um.candidates_token_count
    return {
        "answer": "".join(parts),
        "ttft_ms": round(ttft_ms or 0.0, 1),
        "total_ms": round((time.perf_counter() - t0) * 1000, 1),
        "output_tokens": out_tokens,
        "finish_reason": finish,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL") or ""
    key = os.environ.get("SUPABASE_ANON_KEY") or ""
    if not (url and key and os.environ.get("GEMINI_API_KEY")):
        print("ERROR: SUPABASE_URL / SUPABASE_ANON_KEY / GEMINI_API_KEY 필요",
              file=sys.stderr)
        return 2
    from supabase import create_client
    from google import genai
    sb = create_client(url, key)
    cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    retr = V1RpcRetriever(sb, gemini_embed_fn(), top_k=args.top_k,
                          rpc_name="nexus_hybrid_search_v4_ctx",
                          expand_neighbors=True)

    fixtures = load_fixtures(DEFAULT_FIXTURES)
    records: list[dict] = []
    stats: dict[str, dict[str, list[float]]] = {
        MODEL_A: {"tok": [], "ttft": [], "total": []},
        MODEL_B: {"tok": [], "ttft": [], "total": []},
    }
    failures: list[str] = []

    for i, fx in enumerate(fixtures, 1):
        q = str(fx.get("question", "")).strip()
        res = retr.retrieve(
            {"masked_text": q, "is_critical": False, "critical_matches": [],
             "oos": False, "faq_hit_id": None, "ambiguity": None},
            {"tracks": ["rule"], "intent": "bench"},
        )
        ctx = "\n\n".join(
            f"[{c['breadcrumb']}]\n{c['text'][:2500]}" for c in res["chunks"]
        ) or "(검색 결과 없음)"
        prompt = _PROMPT.format(q=q, ctx=ctx)
        rec = {"id": fx.get("id"), "category": fx.get("category"),
               "question": q,
               "contexts": [{"breadcrumb": c["breadcrumb"],
                             "document_id": c["document_id"],
                             "text": c["text"]} for c in res["chunks"]]}
        for model in (MODEL_A, MODEL_B):
            try:
                r = _gen_stream(cli, model, prompt)
                rec[model] = r
                stats[model]["tok"].append(float(r["output_tokens"] or 0))
                if r["ttft_ms"] is not None:
                    stats[model]["ttft"].append(r["ttft_ms"])
                stats[model]["total"].append(r["total_ms"])
            except Exception as e:
                rec[model] = {"error": f"{type(e).__name__}: {e}"}
                failures.append(f"{fx.get('id')}:{model}")
                print(f"[synth_bench] FAILED {fx.get('id')} {model}: "
                      f"{type(e).__name__}: {e}", file=sys.stderr, flush=True)
        records.append(rec)
        print(f"  … {i}/{len(fixtures)}")

    out = {
        "timestamp": datetime.now().isoformat(),
        "purpose": "3.6 Flash 선행 벤치 — 토큰·지연만. 품질 판정은 Phase 1 "
                   "인용 스코어러로 소급 채점 (합성 모델 교체 금지 규율 유지)",
        "models": {"A_current": MODEL_A, "B_candidate": MODEL_B},
        "config": {"temperature": 0.0, "max_output_tokens": 4096,
                   "thinking": "default(미지정) 양쪽 동일", "mode": "stream, max_output_tokens=4096 (thinking 예산 포함 — MAX_TOKENS 절단 방지)",
                   "context": f"v4-ctx top{args.top_k} + neighbors±2 (동일 투입)"},
        "prompt_template": _PROMPT,
        "records": records,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"synth_bench_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for model in (MODEL_A, MODEL_B):
        s = stats[model]
        n = len(s["tok"])
        print(f"── {model} (성공 {n}/{len(fixtures)}) ──")
        if n:
            print(f"출력 토큰  합계 {sum(s['tok']):.0f}  평균 {sum(s['tok'])/n:.0f}")
            print(f"TTFT       p50 {_pct(s['ttft'], .5):.0f}ms  p95 {_pct(s['ttft'], .95):.0f}ms")
            print(f"총 생성    p50 {_pct(s['total'], .5):.0f}ms  p95 {_pct(s['total'], .95):.0f}ms")
        print()
    a, b = stats[MODEL_A], stats[MODEL_B]
    if a["tok"] and b["tok"]:
        ta, tb = sum(a["tok"]) / len(a["tok"]), sum(b["tok"]) / len(b["tok"])
        print("── Δ (B − A) ──")
        print(f"출력 토큰 평균  {ta:.0f} → {tb:.0f}  ({(tb - ta) / ta * 100:+.1f}%)")
        
        print(f"TTFT p50        {_pct(a['ttft'], .5):.0f}ms → {_pct(b['ttft'], .5):.0f}ms")
        print(f"총 생성 p50     {_pct(a['total'], .5):.0f}ms → {_pct(b['total'], .5):.0f}ms")
        print(f"총 생성 p95     {_pct(a['total'], .95):.0f}ms → {_pct(b['total'], .95):.0f}ms")
    if failures:
        print(f"실패: {failures}", file=sys.stderr)
    print(f"\nWrote {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
