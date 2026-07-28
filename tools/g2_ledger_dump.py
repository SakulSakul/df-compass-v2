"""G2 감사 지원 킷 — 파생 원장 문서별 등재 조항 전수 덤프 (2026-07-28 방식 변경).

용도: Cowork 감리자(파서·원장 무관 독립 채널)가 사규 원문 101건과 전수
대조할 기준표. 문서 제목 + canonical 조항명만 덤프 — 본문 텍스트 미포함.
하단에 인간 표본 재확인용 무작위 추첨 5건(시드 고정) + 필수 1건을 출력.

ADR-8: anon SELECT 전용, DB 쓰기 0. 원장 로직(registry/articles) 무수정 —
load_ledger 를 호출만 한다 (H 구현 금지 안건 무관).

실행: SUPABASE_ANON_KEY=... python tools/g2_ledger_dump.py
"""
from __future__ import annotations

import os
import random
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from compass_engine.registry import load_ledger  # noqa: E402

SEED = 20260728          # 표본 추첨 재현용 고정 시드
SAMPLE_N = 5
MANDATORY = "(인사) 직장 내 괴롭힘 예방·대응지침"   # 07-27 후속 조사 필수 편입


def main() -> int:
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"],
                       os.environ.get("SUPABASE_ANON_KEY")
                       or os.environ["SUPABASE_KEY"])
    ledger = load_ledger(sb)

    titles = sorted(ledger.title_to_doc_id)
    lines = [
        "# G2 파생 원장 전수 덤프 — 기계 전수 대조 기준표",
        f"생성: {datetime.now().isoformat()}  |  tools/g2_ledger_dump.py  |  "
        f"anon SELECT 전용",
        f"문서 {len(titles)}건 · 청크 스캔 {ledger.chunk_rows_scanned}건. "
        "각 문서의 파생 원장 등재 조항 전체(canonical) — 본문 미포함.",
        "",
        "> 수치 해설: registry 기동 로그의 docs_with_articles 는 청크 스캔에",
        "> 잡힌 문서 키 수로 **archived 문서 청크까지 포함**된다 (실측: active",
        "> 101 + archived 19 키 — 2026-07-28 확인). 본 덤프는 active 101건",
        "> 기준이며 §5 verify 도 active 제목으로만 해석하므로 archived 등재분은",
        "> 검증 경로에 관여하지 않는다. 원장 로직은 무수정 (부수 발견 기록만).",
        "",
    ]
    no_article_docs = []
    for t in titles:
        arts = sorted(ledger.articles_by_doc.get(ledger.title_to_doc_id[t], set()),
                      key=str)
        if not arts:
            no_article_docs.append(t)
        lines.append(f"## {t}")
        lines.append(f"- 등재 {len(arts)}건: "
                     + (", ".join(arts) if arts else "(없음)"))
        lines.append("")

    rng = random.Random(SEED)
    pool = [t for t in titles if t != MANDATORY]
    sample = sorted(rng.sample(pool, SAMPLE_N))
    lines += [
        "---",
        "## 인간 표본 재확인 대상 (감사자의 감사)",
        f"- 필수 1건: {MANDATORY}",
        f"- 무작위 {SAMPLE_N}건 (seed={SEED}, 필수 건 제외 풀 {len(pool)}):",
    ]
    lines += [f"  {i}. {t}" for i, t in enumerate(sample, 1)]
    lines += [
        "",
        f"(참고) 등재 0건 문서 {len(no_article_docs)}건: "
        + (", ".join(no_article_docs) if no_article_docs else "없음"),
    ]

    out = (_ROOT / "eval" / "results"
           / f"g2_ledger_dump_{datetime.now().strftime('%Y%m%dT%H%M%S')}.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"docs={len(titles)} no_article_docs={len(no_article_docs)} "
          f"sample={sample}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
