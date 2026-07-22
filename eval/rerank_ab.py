"""리랭커 백엔드 A/B — 검색 하니스로 pass/P/R + 리랭크 지연(p50/p95) 비교.

지시 (2026-07-21): 현행(gemini-2.5-flash-lite) vs gemini-3.5-flash-lite
(thinking 최소). v1 nexus_reranker 의 listwise·JSON 방식을 계측용으로 미러:
pool(top-15, v4-ctx) → listwise 재정렬 → top_k 컷 → 검색 수준 채점.

env: SUPABASE_URL, SUPABASE_ANON_KEY, GEMINI_API_KEY
사용법: python eval/rerank_ab.py [--top-k 3] [--pool 15]

리랭크 실패는 fail-open(원 순서 유지) + 실패 수 보고 — silent 금지.
모델 교체 판단은 이 숫자로만 (계측기 없는 교체 금지 규율).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from compass_engine.stages import IntakeResult, RetrieveResult, RouteResult  # noqa: E402
from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn  # noqa: E402
from eval.runner import DEFAULT_FIXTURES, run_all  # noqa: E402

_PROMPT = """사규 검색 결과를 질문 관련도 순으로 재정렬하세요.

[질문]
{q}

[후보 청크]
{items}

JSON only: {{"order": [가장 관련 높은 것부터 후보 번호 나열]}}"""


class RerankingRetriever:
    """pool(top-N, v4-ctx) → listwise 리랭크(model) → top_k. Retriever 프로토콜."""

    def __init__(self, base: V1RpcRetriever, model: str, *, top_k: int,
                 thinking_level: str | None = None):
        self._base = base
        self.model = model
        self.top_k = top_k
        self.thinking_level = thinking_level
        self.latencies_ms: list[float] = []
        self.failures = 0
        from google import genai
        self._cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def _rerank(self, q: str, chunks: list) -> list:
        items = "\n".join(
            f"{i}. [{c['breadcrumb']}] {c['text'][:300]}"
            for i, c in enumerate(chunks)
        )
        cfg: dict = {
            "temperature": 0.0,
            "max_output_tokens": 256,
            "response_mime_type": "application/json",
        }
        # 3.5 계열은 thinking_budget(구식) 거부 — thinking_level 사용 (400 프로브로 확정)
        if self.thinking_level is not None:
            cfg["thinking_config"] = {"thinking_level": self.thinking_level}
        t0 = time.perf_counter()
        try:
            res = self._cli.models.generate_content(
                model=self.model, contents=_PROMPT.format(q=q, items=items),
                config=cfg,
            )
            self.latencies_ms.append((time.perf_counter() - t0) * 1000)
            m = re.search(r"\{.*\}", getattr(res, "text", "") or "", re.DOTALL)
            order = json.loads(m.group(0))["order"] if m else []
            picked, seen = [], set()
            for idx in order:
                if isinstance(idx, int) and 0 <= idx < len(chunks) and idx not in seen:
                    seen.add(idx)
                    picked.append(chunks[idx])
            for i, c in enumerate(chunks):        # 응답 누락분은 원 순서로 보충
                if i not in seen:
                    picked.append(c)
            return picked
        except Exception as e:
            self.latencies_ms.append((time.perf_counter() - t0) * 1000)
            self.failures += 1
            print(f"[rerank_ab] FAILED ({self.model}): {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            return chunks                          # fail-open — 원 순서

    def retrieve(self, intake: IntakeResult, route: RouteResult) -> RetrieveResult:
        pooled = self._base.retrieve(intake, route)
        chunks = self._rerank(intake["masked_text"], list(pooled["chunks"]))
        return RetrieveResult(
            chunks=chunks[: self.top_k],
            query_set=pooled["query_set"],
            provider=f"rerank:{self.model}",
        )


def _pct(v: list[float], p: float) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--pool", type=int, default=15)
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL") or ""
    key = os.environ.get("SUPABASE_ANON_KEY") or ""
    if not (url and key and os.environ.get("GEMINI_API_KEY")):
        print("ERROR: SUPABASE_URL / SUPABASE_ANON_KEY / GEMINI_API_KEY 필요",
              file=sys.stderr)
        return 2
    from supabase import create_client
    sb = create_client(url, key)
    embed = gemini_embed_fn()

    # A = 현행 / B = 3.5 flash-lite (thinking 최소)
    backends = [
        ("A 현행", "gemini-2.5-flash-lite", None),
        ("B 신형", "gemini-3.5-flash-lite", "minimal"),
    ]
    results = []
    for label, model, tb in backends:
        base = V1RpcRetriever(sb, embed, top_k=args.pool,
                              rpc_name="nexus_hybrid_search_v4_ctx",
                              expand_neighbors=False)
        rr = RerankingRetriever(base, model, top_k=args.top_k, thinking_level=tb)
        s = run_all(rr, fixtures_path=DEFAULT_FIXTURES, top_k=args.top_k)
        results.append((label, model, rr, s))
        lat = rr.latencies_ms
        print(f"── {label} = {model} ──")
        print(f"pass {s.passed}/{s.total}  avg P {s.avg_precision:.3f}  "
              f"avg R {s.avg_recall:.3f}")
        print(f"rerank 지연 p50 {_pct(lat, .5):.0f}ms  p95 {_pct(lat, .95):.0f}ms  "
              f"(호출 {len(lat)}, 실패 {rr.failures})")
        print()

    (la, ma, ra, sa), (lb, mb, rb, sb2) = results
    print("── 개선폭 (B − A) ──")
    print(f"pass   {sa.passed}/{sa.total} → {sb2.passed}/{sb2.total}  "
          f"(Δ {sb2.passed - sa.passed:+d})")
    print(f"avg P  {sa.avg_precision:.3f} → {sb2.avg_precision:.3f}  "
          f"(Δ {sb2.avg_precision - sa.avg_precision:+.3f})")
    print(f"avg R  {sa.avg_recall:.3f} → {sb2.avg_recall:.3f}  "
          f"(Δ {sb2.avg_recall - sa.avg_recall:+.3f})")
    print(f"p50    {_pct(ra.latencies_ms, .5):.0f}ms → {_pct(rb.latencies_ms, .5):.0f}ms")
    print(f"p95    {_pct(ra.latencies_ms, .95):.0f}ms → {_pct(rb.latencies_ms, .95):.0f}ms")
    for fa, fb in zip(sa.fixtures, sb2.fixtures):
        if fa.passed != fb.passed:
            print(f"  {fa.id}: {'✅' if fa.passed else '❌'} → {'✅' if fb.passed else '❌'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
