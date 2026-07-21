"""DF COMPASS v2 · 검색 수준 eval CLI (v1 eval/run.py 이식).

사용법:
    python eval/run.py --dummy                    # 하니스 완주 검증 (오프라인)
    python eval/run.py --v1-rpc                   # v1 RPC 실검색 (ADR-8)
        (env: SUPABASE_URL, SUPABASE_ANON_KEY, GEMINI_API_KEY 필요)
    공통 옵션: [--fixtures eval/fixtures.yaml] [--top-k 3] [--no-write]

두 백엔드 모두 같은 Retriever 프로토콜 — eval A/B 의 구조적 전제.
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
                    help="v1 nexus_hybrid_search_v3_pgroonga RPC 실검색 (ADR-8)")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    if args.dummy == args.v1_rpc:
        print("ERROR: --dummy 또는 --v1-rpc 중 정확히 하나를 지정하세요.",
              file=sys.stderr)
        return 2

    fixtures_path = Path(args.fixtures)
    if not fixtures_path.exists():
        print(f"ERROR: fixtures 파일 없음: {fixtures_path}", file=sys.stderr)
        return 2

    if args.dummy:
        from eval.dummy_retriever import DummyRetriever
        retriever = DummyRetriever(top_k=args.top_k)
        backend = "dummy"
    else:
        import os
        url = os.environ.get("SUPABASE_URL") or ""
        key = os.environ.get("SUPABASE_ANON_KEY") or ""
        if not url or not key:
            print("ERROR: --v1-rpc 는 SUPABASE_URL / SUPABASE_ANON_KEY 필요 "
                  "(ADR-8: anon 키 SELECT 전용).", file=sys.stderr)
            return 2
        try:
            from supabase import create_client
        except ImportError:
            print("ERROR: supabase-py 미설치 — `pip install supabase`.",
                  file=sys.stderr)
            return 2
        from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn
        retriever = V1RpcRetriever(
            create_client(url, key), gemini_embed_fn(), top_k=args.top_k,
        )
        backend = "v1-rpc"

    print(f"Loaded fixtures from {fixtures_path}")
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
