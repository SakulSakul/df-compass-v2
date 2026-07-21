"""DF COMPASS v2 · 검색 수준 eval CLI (v1 eval/run.py 이식).

사용법:
    python eval/run.py --dummy       # 하니스 완주 검증 (오프라인)
    python eval/run.py --v1-rpc     # v1 방식 (v3 RPC, embedding)
    python eval/run.py --v4-ctx     # contextual (v4 RPC, ctx_embedding — 백필 후)
    python eval/run.py --ab         # v1 vs contextual A/B — 개선폭 숫자 출력
        (라이브 백엔드 env: SUPABASE_URL, SUPABASE_ANON_KEY, GEMINI_API_KEY)
    공통 옵션: [--fixtures eval/fixtures.yaml] [--top-k 3] [--no-write]

모든 백엔드가 같은 Retriever 프로토콜 — A/B 는 rpc_name 만 다르다.
검색 수준 채점(문서 제목)이므로 이웃 결합은 eval 에서 끈다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.runner import (  # noqa: E402
    DEFAULT_FIXTURES, FixtureResult, RunSummary, run_all, write_results_json,
)


def _print_table(results: list[FixtureResult]) -> None:
    header = f"{'id':<5} {'category':<14} {'P':>5} {'R':>5} {'best':>7} {'hit':>3} {'pass':>5}"
    print(header)
    print("-" * len(header))
    for r in results:
        flag = "✅" if r.passed else "❌"
        print(f"{r.id:<5} {r.category:<14} {r.precision:>5.2f} {r.recall:>5.2f} "
              f"{r.best_score:>7.4f} {r.hit_count:>3} {flag:>5}")
        if r.note:
            print(f"      └─ {r.note}")


def _print_summary(s: RunSummary) -> None:
    print()
    print(f"Provider: {s.provider}")
    print(f"Total {s.total} | Passed {s.passed} | Failed {s.failed}")
    print(f"Avg precision: {s.avg_precision:.3f}  Avg recall: {s.avg_recall:.3f}")
    print(f"best_score range: min {s.score_min:.4f}  max {s.score_max:.4f}  "
          f"avg {s.score_avg:.4f}")
    print()
    print("By category:")
    for cat, m in s.by_category.items():
        print(f"  {cat:<14} pass {m['passed']:>2}/{m['total']:<2}  "
              f"P {m['avg_precision']:.2f}  R {m['avg_recall']:.2f}  "
              f"score {m['score_avg']:.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="DF COMPASS v2 retrieval eval")
    ap.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--dummy", action="store_true",
                    help="더미 retriever 로 하니스 완주 검증 (오프라인)")
    ap.add_argument("--v1-rpc", action="store_true",
                    help="v1 방식: nexus_hybrid_search_v3_pgroonga (embedding)")
    ap.add_argument("--v4-ctx", action="store_true",
                    help="contextual: nexus_hybrid_search_v4_ctx (ctx_embedding)")
    ap.add_argument("--ab", action="store_true",
                    help="v1 vs contextual A/B — 개선폭 숫자 출력")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    picked = sum([args.dummy, args.v1_rpc, args.v4_ctx, args.ab])
    if picked != 1:
        print("ERROR: --dummy / --v1-rpc / --v4-ctx / --ab 중 정확히 하나를 "
              "지정하세요.", file=sys.stderr)
        return 2

    fixtures_path = Path(args.fixtures)
    if not fixtures_path.exists():
        print(f"ERROR: fixtures 파일 없음: {fixtures_path}", file=sys.stderr)
        return 2

    def _live_retriever(rpc_name: str):
        import os
        url = os.environ.get("SUPABASE_URL") or ""
        key = os.environ.get("SUPABASE_ANON_KEY") or ""
        if not url or not key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY 필요 "
                               "(ADR-8: anon 키 SELECT 전용)")
        try:
            from supabase import create_client
        except ImportError:
            raise RuntimeError("supabase-py 미설치 — `pip install supabase`")
        from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn
        # 검색 수준 채점(제목 기준) — 이웃 결합 off (합성 단계 전용)
        return V1RpcRetriever(
            create_client(url, key), gemini_embed_fn(),
            top_k=args.top_k, rpc_name=rpc_name, expand_neighbors=False,
        )

    print(f"Loaded fixtures from {fixtures_path}")
    try:
        if args.ab:
            print(f"Running A/B (top_k={args.top_k}): v1(v3) vs contextual(v4) ...")
            print()
            a = run_all(_live_retriever("nexus_hybrid_search_v3_pgroonga"),
                        fixtures_path=fixtures_path, top_k=args.top_k)
            b = run_all(_live_retriever("nexus_hybrid_search_v4_ctx"),
                        fixtures_path=fixtures_path, top_k=args.top_k)
            for label, s in (("A = v1(v3)", a), ("B = contextual(v4)", b)):
                print(f"── {label} ──")
                _print_table(s.fixtures)
                _print_summary(s)
                print()
            print("── 개선폭 (B − A) ──")
            print(f"pass   {a.passed}/{a.total} → {b.passed}/{b.total}  "
                  f"(Δ {b.passed - a.passed:+d})")
            print(f"avg P  {a.avg_precision:.3f} → {b.avg_precision:.3f}  "
                  f"(Δ {b.avg_precision - a.avg_precision:+.3f})")
            print(f"avg R  {a.avg_recall:.3f} → {b.avg_recall:.3f}  "
                  f"(Δ {b.avg_recall - a.avg_recall:+.3f})")
            flips = [
                (ra.id, ra.passed, rb.passed)
                for ra, rb in zip(a.fixtures, b.fixtures)
                if ra.passed != rb.passed
            ]
            for fid, pa, pb in flips:
                print(f"  {fid}: {'✅' if pa else '❌'} → {'✅' if pb else '❌'}")
            if not args.no_write:
                for s in (a, b):
                    print(f"Wrote {write_results_json(s)}")
            return 0

        if args.dummy:
            from eval.dummy_retriever import DummyRetriever
            retriever, backend = DummyRetriever(top_k=args.top_k), "dummy"
        elif args.v1_rpc:
            retriever, backend = _live_retriever("nexus_hybrid_search_v3_pgroonga"), "v1-rpc"
        else:
            retriever, backend = _live_retriever("nexus_hybrid_search_v4_ctx"), "v4-ctx"
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(f"Running retrieval (top_k={args.top_k}, backend={backend}) ...")
    print()
    summary = run_all(retriever, fixtures_path=fixtures_path, top_k=args.top_k)
    _print_table(summary.fixtures)
    _print_summary(summary)

    if not args.no_write:
        out = write_results_json(summary)
        print()
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
