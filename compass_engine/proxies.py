"""프록시 문서 명단 — 원문 미확보 상태로 적재된 문서 (심의 2항, wave 2·3).

⓪-3 프로브(2026-08-01): 표준 명명 규칙(`카테고리│담당팀│제목│Rag.docx`)
이탈 2건이 당초 명단이었고, 원문 확보 시 명단에서 제거(승격) — 비차단
병행 트랙.

승격 이력: "(공통) 임직원 징계기준" — 지시서 008(2026-08-16) Kill Criteria
발동. 저장본(v5, row a771e64a)을 현행 정본으로 확인한 사용자 의결 +
청킹 무결성 검사(수위 8종 전부·항목 1~40 결번 0 — penalty_integrity
프로브) 근거로 제거.
"""
from __future__ import annotations

PROXY_DOCS: frozenset[str] = frozenset({
    "(공통) 신세계그룹 CREDO",
})
