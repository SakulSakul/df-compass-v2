"""A2 — 라우팅 소스 사전 검증 (wave 3 착수 전, 읽기 전용).

nexus_documents 의 title·auto_keywords·auto_query_examples 로 문서 카탈로그를
만들고, LLM 라우팅(질의 → 지배문서 top-2)의 골든 질의 히트율을 측정한다.
- 히트 정의: 문항의 기대 인용 문서(expected_citations) 중 ≥1 개가 라우팅
  결과에 포함. 대상 = 기대 인용이 있는 골든 문항 (negative 제외).
- 기준선: ≥90% (kill criteria). 미달 시 wave 3 착수 전 보장 계층 재설계 복귀.
- 홀드아웃 3문항은 이 검증 셋에 포함 금지 (봉인 규칙 — 아직 미작성 상태로
  자연 충족, 파일 존재 시에도 golden.yaml 외 질의는 쓰지 않는다).
결과: eval/results/router_probe_<ts>.json (질의별 라우팅·히트 기록).
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
from eval.runner import RESULTS_DIR, load_fixtures  # noqa: E402

# wave 3 본구현 이후: 정본 라우터(compass_engine.doc_router)를 그대로 측정
# — 계측기와 정본의 드리프트 방지. (A2 1차 프로브는 동일 프롬프트 인라인판)
from compass_engine.doc_router import DocRouter  # noqa: E402


def main() -> int:
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"],
                       os.environ.get("SUPABASE_ANON_KEY")
                       or os.environ["SUPABASE_KEY"])
    router = DocRouter(sb)

    entries = [e for e in load_fixtures(_ROOT / "eval" / "golden.yaml")
               if e.get("expected_citations")]
    records, hits, confident_n = [], 0, 0
    for i, e in enumerate(entries, 1):
        r0 = router.route(e["question"])          # 실패는 내부 no-op
        r = {"docs": r0["doc_titles"], "confident": r0["confident"]}
        expected = [c["doc"] for c in e["expected_citations"]]
        hit = any(d in expected for d in r["docs"])
        hits += hit
        confident_n += r["confident"]
        records.append({"id": e["id"], "category": e.get("category"),
                        "question": e["question"], "expected": expected,
                        "routed": r["docs"], "confident": r["confident"],
                        "hit": hit})
        print(f"… {i}/{len(entries)} {e['id']} hit={hit}", flush=True)

    rate = hits / len(entries)
    out = {"timestamp": datetime.now().isoformat(), "model": router.model,
           "catalog_source": "nexus_documents(title,auto_keywords,auto_query_examples)",
           "n": len(entries), "hits": hits, "hit_rate": round(rate, 4),
           "confident_n": confident_n, "records": records}
    path = RESULTS_DIR / f"router_probe_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n라우팅 히트율: {hits}/{len(entries)} ({rate:.1%})  "
          f"confident={confident_n}/{len(entries)}")
    misses = [r["id"] for r in records if not r["hit"]]
    print(f"미스: {misses}")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
