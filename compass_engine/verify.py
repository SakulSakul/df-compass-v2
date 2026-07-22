"""§5 조항 검증기 — verify 스테이지 (Phase 1 ⑥). 결정론 — LLM 판단 금지.

DESIGN §5 스펙 그대로:
  답변에서 (문서명, 조항번호) 쌍 추출 → 원장 대조
    → 실재: 통과
    → 문서는 있는데 조항 없음(article_missing): 신뢰도 강등 + trace 기록
      (스펙의 "제거·재합성 또는 강등" 중 강등 채택 — 재합성 루프는 후속)
    → 문서 자체 없음(document_missing): 답변 차단 → 강등 재시도/담당부서 라우팅
추출·대조는 citations.py(⓪ 스코어러와 동일 코어) — 계측기와 정본의 드리프트 방지.
섹션 계약 검사는 synthesis.check_section_contract 재사용.

confidence(간이, Phase 1): ok / (ok+article_missing+document_missing).
인용이 하나도 없으면 0.0 (근거 미제시 — 강등 사유는 아님, 신호로만).
멀티시그널 confidence 는 ⑩ 베이스라인 확정 국면에서 확장.
"""
from __future__ import annotations

import sys

from .citations import check_citations
from .registry import ArticleLedger
from .stages import CitationCheck, VerifyResult
from .synthesis import check_section_contract


def verify_answer(answer: str, ledger: ArticleLedger) -> VerifyResult:
    checks = check_citations(answer, ledger)
    cits: list[CitationCheck] = [
        {"document_title": c.title or "", "article_no": c.canonical,
         "verdict": ("ok" if c.verdict == "ok"
                     else "document_missing" if c.verdict == "document_missing"
                     else "article_missing")}
        for c in checks if c.verdict != "unattributed"
    ]
    n_ok = sum(1 for c in cits if c["verdict"] == "ok")
    n_am = sum(1 for c in cits if c["verdict"] == "article_missing")
    n_dm = sum(1 for c in cits if c["verdict"] == "document_missing")

    if n_dm > 0:
        action = "block"            # 비실재 문서 인용 — 답변 차단 (서열 1위)
    elif n_am > 0:
        action = "degrade"          # 비실재 조항 — 신뢰도 강등 표시
    else:
        action = "pass"

    denom = n_ok + n_am + n_dm
    confidence = (n_ok / denom) if denom else 0.0
    contract_ok = check_section_contract(answer)

    if action != "pass":
        print(f"[verify] {action}: ok={n_ok} article_missing={n_am} "
              f"document_missing={n_dm}", file=sys.stderr, flush=True)
    return VerifyResult(
        citations=cits, section_contract_ok=contract_ok,
        confidence=round(confidence, 4), action=action,
    )
