"""intake 스테이지 (Phase 1 ⑧ — critical 게이트 + pii, v1 순서 무수정 미러).

v1 core/chatbot.ask 의 실측 순서 그대로 (2026-07-22 확인):
  ① mask_pii(원문)  ② load_keywords  ③ detect(원문) → 미발동 시 detect(masked)
critical 판정은 **retrieve·synthesize 이전**에 일어나고, triggered 답변은
enforce_structure(4단 + 핫라인 박스)로 핫라인 우선 구성된다. v1 은 critical
이어도 검색·합성을 생략하지 않는다(안전 카테고리 확장 + critical 프롬프트) —
v2 도 동일. v1 의 FAQ/OOS/askback fast-path 차단(not triggered 가드)은
해당 fast-path 가 v2 에 생기는 Phase 3 에서 같은 가드로 이식한다.

모듈은 전부 v1port(무수정 복사본) 사용 — 로직 재작성 없음.
"""
from __future__ import annotations

from typing import Any

from .stages import IntakeResult
from .v1port.critical_mode import detect, load_keywords
from .v1port.pii_filter import mask_pii


def run_intake(supabase: Any, question: str,
               extra_pii_terms: list[str] | None = None) -> IntakeResult:
    masked = mask_pii(question, extra_pii_terms or [])
    keywords = load_keywords(supabase)
    detection = detect(question, keywords)          # v1: 원문 우선
    if not detection.triggered:
        detection = detect(masked, keywords)        # v1: masked 재검사
    return IntakeResult(
        masked_text=masked,
        is_critical=detection.triggered,
        critical_kind=detection.kind,
        critical_matches=list(detection.matched),
        oos=False, faq_hit_id=None, ambiguity=None,  # Phase 3 범위
    )
