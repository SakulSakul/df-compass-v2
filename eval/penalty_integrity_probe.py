"""지시서 008-A — (공통) 임직원 징계기준 청킹 무결성 검사 (읽기 전용).

A0 판정(2026-08-16): 독립 원문 소재 부재 — nexus_documents 에 원문 텍스트
컬럼 없음·source_storage_path=None·storage 버킷 0·v1 repo 내 DOCX 부재.
∴ 지시서 해석 규칙 발동: "정본↔적재 일치" 검사는 성립 불가, 본 검사는
**청킹 무결성 검사**(내부 일관성 — 누락·절단·왜곡 신호 검출)로 수행한다.
정본성 자체는 사용자(운영자) 의결(2026-08-16, 저장본=현행 정본 v5)에 근거.

검사 항목:
1. 청크 전수 원시 덤프 (id·길이·본문)
2. 징계 수위 명단 출현 맵 — 서면경고~징계해직 등 8종 + 양정(가중/감경) 조건
3. 문서 구조 신호 — 표제·장 번호(1.~) 출현, 항목 번호 연속성(결번 검출)
4. 청크 간 완전 중복 / 빈 청크 / 비정상 길이

산출: eval/results/penalty_integrity_<ts>.json (무편집 원시)
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

from eval.runner import RESULTS_DIR  # noqa: E402

DOC_ID = "a771e64a-cee6-4080-845a-564ff016302b"
SEVERITIES = ["경고장", "서면경고", "견책", "감급", "감봉", "정직", "강격",
              "징계해직"]
CONDITIONS = ["가중", "감경", "자진 신고", "자진신고", "관리책임", "인사위원회"]


def main() -> int:
    sb = create_client(os.environ["SUPABASE_URL"],
                       os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    chunks = (sb.table("nexus_chunks")
              .select("id,text,token_count,article_no,case_no")
              .eq("document_id", DOC_ID).execute().data or [])
    full = "\n".join(c.get("text") or "" for c in chunks)

    sev_map = {s: full.count(s) for s in SEVERITIES}
    cond_map = {c_: full.count(c_) for c_ in CONDITIONS}
    # 항목 번호(비위행위 목록 "N. ") 수집 → 결번 검출
    nums = sorted({int(m) for m in re.findall(r"(?:^|\n)(\d{1,2})\.\s", full)})
    missing = [n for n in range(min(nums), max(nums) + 1)
               if n not in nums] if nums else []
    texts = [(c.get("text") or "") for c in chunks]
    dup = len(texts) - len(set(texts))
    empty = sum(1 for t in texts if not t.strip())

    out = {
        "timestamp": datetime.now().isoformat(),
        "doc_id": DOC_ID,
        "a0_source_finding": {
            "documents_text_column": None,
            "source_storage_path": "None",
            "storage_buckets": 0,
            "v1_repo_docx": False,
            "verdict": "독립 원문 부재 → 청킹 무결성 검사로 수행 (정본성=사용자 의결 08-16, v5)",
        },
        "n_chunks": len(chunks),
        "total_chars": len(full),
        "severity_map": sev_map,
        "severity_all_present": all(v > 0 for v in sev_map.values()),
        "condition_map": cond_map,
        "title_header_present": "임직원 징계기준" in full,
        "item_numbers": {"min": nums[0] if nums else None,
                         "max": nums[-1] if nums else None,
                         "count": len(nums), "missing": missing},
        "duplicate_chunks": dup,
        "empty_chunks": empty,
        "chunks": [{"id": c["id"], "len": len(c.get("text") or ""),
                    "token_count": c.get("token_count"),
                    "article_no": c.get("article_no"),
                    "text": c.get("text")} for c in chunks],
    }
    path = RESULTS_DIR / f"penalty_integrity_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "chunks"},
                     ensure_ascii=False, indent=1))
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
