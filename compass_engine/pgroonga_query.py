"""pgroonga &@~ 쿼리 빌더 — v1 nexus_build_pgroonga_query 최소 이식 (Phase 1 ③).

v1 SQL 검증(2026-05-13) 그대로: &@~ 는 띄어쓰기를 AND 로 해석 → recall 처참.
명시적 " OR " 결합 필수. 토큰화 + 조사 제거 + 중복 제거까지가 이식 범위 —
v1 의 동의어/incident taxonomy 확장은 사전(dict) 의존이라 미이식
(synonym_dictionary 연동은 Phase 3 boost/intake 계열에서 재설계 — ADR-5).
"""
from __future__ import annotations

import re

_KOREAN_PARTICLES = (
    "으로부터", "에서부터", "에게서", "한테서", "이라고", "라고",
    "에서", "에게", "한테", "으로", "까지", "부터", "마다",
    "이라", "처럼", "보다", "조차", "마저",
    "이", "가", "을", "를", "은", "는", "도", "만",
    "와", "과", "의", "에", "로", "랑",
)

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")


def build_pgroonga_query(text: str) -> str:
    """자연어 질문 → pgroonga OR 쿼리. 예: '고객이 매장에' → '고객 OR 매장'."""
    if not text:
        return ""
    cleaned: list[str] = []
    for tok in _TOKEN.findall(text):
        for p in _KOREAN_PARTICLES:
            if tok.endswith(p) and len(tok) > len(p) + 1:
                tok = tok[: -len(p)]
                break
        if len(tok) >= 2:
            cleaned.append(tok)
    seen: set[str] = set()
    uniq = [t for t in cleaned if not (t in seen or seen.add(t))]
    return " OR ".join(uniq)
