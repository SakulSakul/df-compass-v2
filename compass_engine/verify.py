"""§5 조항 검증기 — verify 스테이지 (Phase 1 ⑥ → wave 2 개정). 결정론 — LLM 판단 금지.

DESIGN §5 스펙 그대로:
  답변에서 (문서명, 조항번호) 쌍 추출 → 원장 대조
    → 실재: 통과
    → 문서는 있는데 조항 없음(article_missing): 신뢰도 강등 + trace 기록
    → 문서 자체 없음(document_missing): 답변 차단
추출·대조는 citations.py(⓪ 스코어러와 동일 코어) — 계측기와 정본의 드리프트 방지.
**pass/degrade/block 분기 로직은 wave 2 에서 1비트도 변경하지 않았다** —
입력(checks 목록)만 확장: ① A1 법령 앵커는 citations 단계에서 대조 제외
② 문서명 실재 검증(NEXUS_ENABLE_DOCNAME_CHECK, 기본 on)이 명시 인용
형식(「」·[참조:])의 비실재 문서명을 document_missing 으로 추가.

grade (wave 2 — 심의 3항: 연속값 confidence 폐기 → 결정론 서수 4등급):
  LOW        : 강등·차단 발생 (action != pass)
  UNVERIFIED : 사규 앵커 쌍 0 — 문서수준 인용·법령 전용·무인용 (0.0 으로
               뭉개지 않는 별도 상태. 앵커 0 정체 = 문서수준 45/52 실측)
  MEDIUM     : 앵커 ok 있으나 프록시 문서(proxies.PROXY_DOCS) 인용 포함 —
               상한 (HIGH 세탁 방지. 문서수준 출현까지 넓게 잡음 — 안전 측)
  HIGH       : 원문 문서의 사규 앵커 ok ≥1 + 프록시 미포함 + 강등 없음
앵커 수는 포화 반영만 — ok ≥1 스텝 함수 (선형 가중 금지, 심의 확정).
"""
from __future__ import annotations

import os
import sys

from .citations import check_citations, check_document_names
from .proxies import PROXY_DOCS
from .registry import ArticleLedger
from .stages import CitationCheck, VerifyResult
from .synthesis import check_section_contract


def _grade(n_ok: int, action: str, proxy_cited: bool) -> str:
    if action != "pass":
        return "LOW"
    if n_ok == 0:                      # 사규 앵커 0 (포화 스텝의 0단)
        return "UNVERIFIED"
    return "MEDIUM" if proxy_cited else "HIGH"


def verify_answer(answer: str, ledger: ArticleLedger, *,
                  synthesis_integrity_ok: bool = True) -> VerifyResult:
    """synthesis_integrity_ok=False (R3 g02 게이트 — 재합성 후에도 계약
    미충족) 이면 pass 를 degrade 로 격상한다 (R2 심의 의결분 — 기존
    카운트 기반 3분기 자체는 불변, 격상만 추가)."""
    checks = check_citations(answer, ledger)
    # wave 2 확장 — 명시 인용 문서명 실재 검증 (플래그, 기본 on)
    if os.environ.get("NEXUS_ENABLE_DOCNAME_CHECK", "true").lower() == "true":
        checks = checks + check_document_names(answer, ledger)
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
    if action == "pass" and not synthesis_integrity_ok:
        action = "degrade"          # R3 g02 게이트 — 계약 미충족 답변 강등

    proxy_cited = any(c["document_title"] in PROXY_DOCS for c in cits) or \
        any(t in answer for t in PROXY_DOCS)
    grade = _grade(n_ok, action, proxy_cited)
    contract_ok = check_section_contract(answer)

    if action != "pass":
        print(f"[verify] {action}: ok={n_ok} article_missing={n_am} "
              f"document_missing={n_dm}", file=sys.stderr, flush=True)
    return VerifyResult(
        citations=cits, section_contract_ok=contract_ok,
        grade=grade, action=action,
    )
