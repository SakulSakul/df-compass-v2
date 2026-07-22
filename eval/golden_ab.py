"""3.6 Flash 정식 A/B — golden 52문항, 합성 모델 채택 판정 (Phase 1 ⑦ 후속).

현행(gemini-3.5-flash) vs gemini-3.6-flash. 동일 컨텍스트(v4-ctx top3+이웃)·
동일 프롬프트. 인용 지시는 golden 원칙 반영: **발췌에 조항 번호가 명시된
경우에만 (문서명, 제N조), 아니면 문서명만** (제N조 강제가 위조를 유도한
2026-07-22 벤치 교훈).

채점 (모두 결정론):
- 기대 인용 재현율: expected_citations 의 (doc[, article]) 이 답변에서
  ok 판정 쌍으로 등장하는 비율 (doc-level 기대는 문서 인용만으로 충족)
- 위조율: has_fabrication 답변 수 (품질 서열 1위)
- negative pass: 무응답 표명 + ok 0 + 위조 0
- 효율: 출력 토큰·총 생성시간 p50/p95

env: SUPABASE_URL, SUPABASE_ANON_KEY(검색), SUPABASE_SERVICE_KEY(원장), GEMINI_API_KEY
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from compass_engine.citations import check_citations, summarize_checks  # noqa: E402
from compass_engine.registry import load_ledger  # noqa: E402
from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn  # noqa: E402
from eval.runner import RESULTS_DIR, load_fixtures  # noqa: E402
from eval.rerank_ab import _pct  # noqa: E402

MODEL_A = "gemini-3.5-flash"
MODEL_B = "gemini-3.6-flash"

_PROMPT = """당신은 신세계디에프 사규 안내 챗봇입니다. 아래 [사규 발췌]만 근거로
질문에 답하세요.

인용 규칙 (반드시 준수):
- 발췌 표제([문서명>조항])나 본문에 조항 번호가 **명시된 경우에만**
  (문서명, 제N조) 형식으로 인용하세요.
- 조항 번호가 보이지 않으면 **문서명만** 괄호로 인용하세요. 조항 번호를
  추측하거나 만들어내지 마세요.
- 발췌에 없는 내용은 지어내지 말고 "확인 필요"로 표시하세요.
- 질문이 사규와 무관하면 "사규에서 확인되지 않는 내용"이라고 답하세요.

[질문]
{q}

[사규 발췌]
{ctx}"""

_NEG_MARKERS = ("확인 필요", "사규에 없", "사규에서 확인되지 않", "규정이 없",
                "범위를 벗어", "범위 밖", "확인되지 않는")


def _gen(cli, model: str, prompt: str) -> dict:
    t0 = time.perf_counter()
    ttft = None
    parts, out_tokens, finish = [], None, None
    for ev in cli.models.generate_content_stream(
        model=model, contents=prompt,
        config={"temperature": 0.0, "max_output_tokens": 4096},
    ):
        txt = getattr(ev, "text", "") or ""
        if txt and ttft is None:
            ttft = (time.perf_counter() - t0) * 1000
        parts.append(txt)
        cand = (getattr(ev, "candidates", None) or [None])[0]
        if cand is not None and getattr(cand, "finish_reason", None):
            finish = str(cand.finish_reason)
        um = getattr(ev, "usage_metadata", None)
        if um is not None and getattr(um, "candidates_token_count", None):
            out_tokens = um.candidates_token_count
    return {"answer": "".join(parts), "ttft_ms": round(ttft or 0, 1),
            "total_ms": round((time.perf_counter() - t0) * 1000, 1),
            "output_tokens": out_tokens, "finish_reason": finish}


def _score(answer: str, entry: dict, ledger) -> dict:
    checks = check_citations(answer, ledger)
    s = summarize_checks(checks)
    ok_pairs = {(c.title, c.canonical) for c in checks if c.verdict == "ok"}
    ok_docs = {t for t, _ in ok_pairs}
    exp = entry.get("expected_citations") or []
    hit = 0
    for e in exp:
        doc, art = e.get("doc"), e.get("article")
        if art is None:
            # doc-level 기대: 인용 지시가 "조항 없으면 문서명만"이므로
            # 문서명 출현(접두어 생략 포함)으로 판정 — 조항 앵커 추출기는
            # 조항 없는 문서 인용을 못 잡는다 (1차 채점 아티팩트 수정)
            import re as _re
            stripped = _re.sub(r"^\([^)]{1,12}\)\s*", "", doc)
            hit += 1 if (doc in answer or stripped in answer) else 0
        else:
            hit += 1 if (doc, art) in ok_pairs else 0
    s["expected_total"] = len(exp)
    s["expected_hit"] = hit
    if entry.get("category") == "negative":
        s["negative_pass"] = (
            s["ok"] == 0 and not s["has_fabrication"]
            and any(m in answer for m in _NEG_MARKERS)
        )
    return s


def main() -> int:
    from supabase import create_client
    from google import genai
    url = os.environ["SUPABASE_URL"]
    sb_search = create_client(url, os.environ["SUPABASE_ANON_KEY"])
    sb_ledger = create_client(url, os.environ.get("SUPABASE_SERVICE_KEY")
                              or os.environ["SUPABASE_ANON_KEY"])
    cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    ledger = load_ledger(sb_ledger)
    retr = V1RpcRetriever(sb_search, gemini_embed_fn(), top_k=3,
                          rpc_name="nexus_hybrid_search_v4_ctx",
                          expand_neighbors=True)
    entries = load_fixtures(_ROOT / "eval" / "golden.yaml")

    records = []
    agg = {m: {"tok": [], "ttft": [], "total": [], "exp_hit": 0, "exp_total": 0,
               "fab": 0, "neg_pass": 0, "neg_total": 0, "nonstop": 0}
           for m in (MODEL_A, MODEL_B)}
    for i, e in enumerate(entries, 1):
        q = e["question"]
        res = retr.retrieve(
            {"masked_text": q, "is_critical": False, "critical_matches": [],
             "oos": False, "faq_hit_id": None, "ambiguity": None},
            {"tracks": ["rule"], "intent": "golden_ab"})
        ctx = "\n\n".join(f"[{c['breadcrumb']}]\n{c['text'][:2500]}"
                          for c in res["chunks"]) or "(검색 결과 없음)"
        prompt = _PROMPT.format(q=q, ctx=ctx)
        rec = {"id": e["id"], "category": e.get("category"), "question": q}
        for m in (MODEL_A, MODEL_B):
            try:
                g = _gen(cli, m, prompt)
                sc = _score(g["answer"], e, ledger)
                rec[m] = {**g, "score": sc}
                a = agg[m]
                a["tok"].append(float(g["output_tokens"] or 0))
                a["ttft"].append(g["ttft_ms"])
                a["total"].append(g["total_ms"])
                a["exp_hit"] += sc["expected_hit"]
                a["exp_total"] += sc["expected_total"]
                a["fab"] += 1 if sc["has_fabrication"] else 0
                if "negative_pass" in sc:
                    a["neg_total"] += 1
                    a["neg_pass"] += 1 if sc["negative_pass"] else 0
                if g["finish_reason"] != "FinishReason.STOP":
                    a["nonstop"] += 1
            except Exception as ex:
                rec[m] = {"error": f"{type(ex).__name__}: {ex}"}
                print(f"[golden_ab] FAILED {e['id']} {m}: {ex}",
                      file=sys.stderr, flush=True)
        records.append(rec)
        print(f"… {i}/{len(entries)}", flush=True)

    out = {"timestamp": datetime.now().isoformat(),
           "models": {"A": MODEL_A, "B": MODEL_B},
           "prompt_template": _PROMPT, "records": records}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"golden_ab_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n════ 정식 A/B 결과 (golden 52) ════")
    for m in (MODEL_A, MODEL_B):
        a = agg[m]
        n = len(a["tok"])
        er = a["exp_hit"] / a["exp_total"] if a["exp_total"] else 0
        print(f"── {m} (완주 {n}/52, 비정상 finish {a['nonstop']}) ──")
        print(f"기대 인용 재현율 {a['exp_hit']}/{a['exp_total']} ({er:.1%})")
        print(f"위조 인용 답변  {a['fab']}/52")
        print(f"negative pass   {a['neg_pass']}/{a['neg_total']}")
        print(f"출력 토큰 평균  {sum(a['tok'])/n:.0f}   "
              f"TTFT p50 {_pct(a['ttft'], .5):.0f}ms   "
              f"총생성 p50 {_pct(a['total'], .5):.0f}ms  p95 {_pct(a['total'], .95):.0f}ms")
        print()
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
