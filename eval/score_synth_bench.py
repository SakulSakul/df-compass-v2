"""synth_bench 저장본 소급 채점 — 3.6 Flash 품질 판정 (Phase 1 ⓪).

저장된 답변 전문(재실행 불요)을 §5 인용 스코어러로 채점:
답변별 (문서명, 조항) 쌍 → 파생 원장 대조 → ok / article_missing /
document_missing / unattributed 집계 + 위조 인용(has_fabrication) 플래그.

원장은 라이브 v1 DB 에서 로드 (registry.load_ledger — SELECT 전용).
env: SUPABASE_URL + SUPABASE_SERVICE_KEY(읽기용) 또는 SUPABASE_ANON_KEY
사용법: python eval/score_synth_bench.py [--file eval/results/synth_bench_*.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from compass_engine.citations import check_citations, summarize_checks  # noqa: E402
from compass_engine.registry import load_ledger  # noqa: E402
from eval.runner import RESULTS_DIR  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None)
    args = ap.parse_args()

    path = args.file or (sorted(glob.glob(str(RESULTS_DIR / "synth_bench_*.json")))
                         or [None])[-1]
    if not path:
        print("ERROR: synth_bench 저장본 없음", file=sys.stderr)
        return 2

    url = os.environ.get("SUPABASE_URL") or ""
    key = (os.environ.get("SUPABASE_SERVICE_KEY")
           or os.environ.get("SUPABASE_ANON_KEY") or "")
    if not (url and key):
        print("ERROR: SUPABASE_URL + (SUPABASE_SERVICE_KEY|SUPABASE_ANON_KEY) 필요",
              file=sys.stderr)
        return 2
    from supabase import create_client
    ledger = load_ledger(create_client(url, key))

    d = json.loads(Path(path).read_text(encoding="utf-8"))
    models = list(d["models"].values())
    agg = {m: {"answers": 0, "total": 0, "ok": 0, "article_missing": 0,
               "document_missing": 0, "unattributed": 0,
               "fabricated_answers": 0, "cited_answers": 0} for m in models}
    rows = []
    for r in d["records"]:
        row = {"id": r["id"]}
        for m in models:
            ans = r.get(m, {}).get("answer", "")
            s = summarize_checks(check_citations(ans, ledger))
            a = agg[m]
            a["answers"] += 1
            for k in ("total", "ok", "article_missing", "document_missing",
                      "unattributed"):
                a[k] += s[k]
            if s["has_fabrication"]:
                a["fabricated_answers"] += 1
            if s["ok"] > 0:
                a["cited_answers"] += 1
            row[m] = s
        rows.append(row)

    print(f"소급 채점: {path}")
    print(f"원장: docs={len(ledger.title_to_doc_id)} "
          f"chunks_scanned={ledger.chunk_rows_scanned}\n")
    hdr = f"{'id':<5}" + "".join(f"{m:>34}" for m in models)
    print(hdr + "\n" + "-" * len(hdr))
    for row in rows:
        cells = []
        for m in models:
            s = row[m]
            fab = "🚨" if s["has_fabrication"] else "  "
            cells.append(f"ok {s['ok']}/{s['total']} am{s['article_missing']} "
                         f"dm{s['document_missing']} un{s['unattributed']}{fab}")
        print(f"{row['id']:<5}" + "".join(f"{c:>34}" for c in cells))
    print()
    for m in models:
        a = agg[m]
        vr = a["ok"] / a["total"] if a["total"] else 0.0
        print(f"── {m} ──")
        print(f"인용 쌍 {a['total']}  ok {a['ok']} ({vr:.1%})  "
              f"article_missing {a['article_missing']}  "
              f"document_missing {a['document_missing']}  "
              f"unattributed {a['unattributed']}")
        print(f"답변 16 중: 검증 인용 보유 {a['cited_answers']}  "
              f"**위조 인용 포함 {a['fabricated_answers']}** (품질 서열 1위 지표)")
        print()

    out = RESULTS_DIR / f"citation_score_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out.write_text(json.dumps(
        {"scored_file": str(path), "aggregate": agg, "per_fixture": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
