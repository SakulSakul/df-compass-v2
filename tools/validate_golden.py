"""golden testset 자가 검증 — 기대 인용의 실재성을 파생 원장으로 확인.

"자(尺)가 틀리면 이후 모든 측정이 틀린다" — testset 오류를 머지 전에 거른다.
검사: ① id 유일성·문항수(≥50)·카테고리 분포 ② 비-negative 는 expected_sources
필수 ③ expected_citations.doc = 원장 정식 제목과 정확 일치 ④ article 지정 시
해당 문서 원장에 실재 ⑤ negative 는 citations/sources 빈 값.

env: SUPABASE_URL + SUPABASE_SERVICE_KEY|SUPABASE_ANON_KEY
사용법: python tools/validate_golden.py [--file eval/golden.yaml]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from compass_engine.registry import load_ledger  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(_ROOT / "eval" / "golden.yaml"))
    args = ap.parse_args()

    import yaml
    data = yaml.safe_load(Path(args.file).read_text(encoding="utf-8")) or []

    url = os.environ.get("SUPABASE_URL") or ""
    key = (os.environ.get("SUPABASE_SERVICE_KEY")
           or os.environ.get("SUPABASE_ANON_KEY") or "")
    if not (url and key):
        print("ERROR: SUPABASE creds 필요", file=sys.stderr)
        return 2
    from supabase import create_client
    ledger = load_ledger(create_client(url, key))

    errors: list[str] = []
    ids = [e.get("id") for e in data]
    dup = [i for i, c in Counter(ids).items() if c > 1]
    if dup:
        errors.append(f"id 중복: {dup}")
    if len(data) < 50:
        errors.append(f"문항수 {len(data)} < 50")

    for e in data:
        eid = e.get("id", "?")
        cat = e.get("category", "")
        cits = e.get("expected_citations") or []
        srcs = e.get("expected_sources") or []
        if cat == "negative":
            if cits or srcs:
                errors.append(f"{eid}: negative 인데 기대 인용/소스 비어있지 않음")
            continue
        if not srcs:
            errors.append(f"{eid}: expected_sources 비어 있음 (비-negative)")
        if not cits:
            errors.append(f"{eid}: expected_citations 비어 있음 (비-negative)")
        for c in cits:
            doc, art = c.get("doc"), c.get("article")
            if not ledger.has_document_title(doc):
                errors.append(f"{eid}: 문서 부재 — {doc!r}")
                continue
            if art is not None:
                did = ledger.title_to_doc_id[doc]
                if art not in ledger.articles_by_doc.get(did, set()):
                    errors.append(f"{eid}: {doc} 에 {art} 표기 부재 (원장 기준)")

    print(f"문항 {len(data)}개 | 분포: {dict(Counter(e.get('category') for e in data))}")
    if errors:
        print(f"\nFAIL — {len(errors)}건:")
        for e in errors:
            print("  ❌", e)
        return 1
    print("PASS — 기대 인용 전부 원장 실재 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
