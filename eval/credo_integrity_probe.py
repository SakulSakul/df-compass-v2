"""지시서 009-A — (공통) 신세계그룹 CREDO 청킹 무결성 검사 (읽기 전용).

A0(2026-08-16 밤): row aedc97fe — source_storage_path=None·storage 버킷 0
(008 실측과 동일 환경) → 독립 원문 부재, 유일 저장본 = nexus_chunks 22청크.
∴ 008 동형: 청킹 무결성 검사로 수행. 정본성 = 사용자 정본 확인 의결(08-16).

조문형 검사 항목:
1. 청크 전수 원시 덤프
2. 조번호 분포 — CREDO 는 장(제1~5장)별 제1~4조 반복 구조: canonical 집합·
   장 구조 마커 실재, 핵심 조항(제4조 금품/향응) 실재
3. 원장(레지스트리) 앵커 등재 — 승격 시 앵커가 원장 대조 검증 대상이 되는
   전제 확인: ledger.verify(CREDO, 제N조) 전수
4. 빈/중복 청크·표제 청크

산출: eval/results/credo_integrity_<ts>.json (무편집)
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
from supabase import create_client  # noqa: E402

from compass_engine.registry import load_ledger  # noqa: E402
from eval.runner import RESULTS_DIR  # noqa: E402

TITLE = "(공통) 신세계그룹 CREDO"


def main() -> int:
    sb = create_client(os.environ["SUPABASE_URL"],
                       os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    doc = sb.table("nexus_documents").select("id,source_filename,version") \
            .eq("title", TITLE).execute().data[0]
    chunks = (sb.table("nexus_chunks").select("id,text,article_no,token_count")
              .eq("document_id", doc["id"]).execute().data or [])
    full = "\n".join(c.get("text") or "" for c in chunks)

    arts = sorted({c.get("article_no") for c in chunks if c.get("article_no")})
    chapters = sorted(set(re.findall(r"제\s?(\d)\s?장", full)))
    ledger = load_ledger(sb)
    ledger_check = {a: ledger.verify(TITLE, a) for a in arts}
    texts = [(c.get("text") or "") for c in chunks]

    out = {
        "timestamp": datetime.now().isoformat(),
        "doc_id": doc["id"],
        "source_filename": doc.get("source_filename"),
        "a0_source_finding": {
            "documents_text_column": None,
            "source_storage_path": None,
            "verdict": "독립 원문 부재 → 청킹 무결성 검사 (정본성=사용자 의결 08-16)",
        },
        "n_chunks": len(chunks),
        "total_chars": len(full),
        "article_canonicals": arts,
        "chapters_found": chapters,
        "key_article_clause": {
            "제4조_금품향응": "금품/향응/편의 수수 및 제공 금지" in full,
            "제2조_기본책무": "사원의 기본책무" in full,
            "지인거래_신고": "지인거래 신고" in full,
        },
        "ledger_anchor_check": ledger_check,
        "ledger_all_ok": all(v == "ok" for v in ledger_check.values()),
        "title_chunk_present": "신세계 CREDO" in full,
        "duplicate_chunks": len(texts) - len(set(texts)),
        "empty_chunks": sum(1 for t in texts if not t.strip()),
        "chunks": [{"id": c["id"], "article_no": c.get("article_no"),
                    "len": len(c.get("text") or ""),
                    "token_count": c.get("token_count"),
                    "text": c.get("text")} for c in chunks],
    }
    path = RESULTS_DIR / f"credo_integrity_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "chunks"},
                     ensure_ascii=False, indent=1))
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
