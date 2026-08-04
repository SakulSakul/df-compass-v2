"""홀드아웃 3문항 재검증 러너 — v2 정본 파이프라인 (봉인 파일 유일 소비처).

통과 기준: 3문항 회수 (expected 문서가 최종 컨텍스트 포함 — 검색 수준).
0 회수 시 kill criteria (질의 재작성 계층 신규 심의). 답변 인용 여부 병기.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from eval.runner import RESULTS_DIR  # noqa: E402


def main() -> int:
    import yaml
    from eval.compare_v1v2 import Harness
    rows = yaml.safe_load((_ROOT / "eval" / "holdout.yaml").read_text(encoding="utf-8"))
    h = Harness()
    strip = lambda t: re.sub(r"^\([^)]{1,12}\)\s*", "", t)  # noqa: E731
    records, recovered = [], 0
    for r in rows:
        side = h.run_v2_side(r["question"])
        ctx = side.get("context_docs") or []
        hit = any(any(e == c or strip(e) == strip(c) for c in ctx)
                  for e in r["expected"])
        cited = any(e in side["answer"] or strip(e) in side["answer"]
                    for e in r["expected"])
        recovered += hit
        records.append({**r, "recovered": hit, "cited_in_answer": cited,
                        "context_docs": ctx, "router_hit": side.get("router_hit"),
                        "verify": side.get("verify"), "answer": side["answer"],
                        "elapsed_total_s": side.get("elapsed_total_s"),
                        "n_chunks": side.get("n_chunks")})
        print(f"{r['id']} recovered={hit} cited={cited} router_hit={side.get('router_hit')}",
              flush=True)
    out = {"timestamp": datetime.now().isoformat(),
           "recovered": recovered, "n": len(rows), "records": records}
    path = RESULTS_DIR / f"holdout_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n홀드아웃 회수: {recovered}/{len(rows)}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
