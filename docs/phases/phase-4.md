# Phase 4 — 확장·자동화

진입 조건: Phase 3 승인.

## 산출물

1. **code/skill 어댑터**: SKILL.md(frontmatter 메타 + 헤딩 단위, description은
   별도 chunk 승격) · code(AST symbol 단위, docstring+시그니처 대표 텍스트).
   source_type별 RLS 노출 정책 필수 — 사규 질문에 code chunk 오염 금지 (라우팅 필터).
2. **git-diff 증분 적재 CI**: 파일 해시 비교 → 변경분만 재파싱·재임베딩.
   재적재 원자 단위 규칙(§3) 준수.
3. **auto testset 연결**: 적재 시 생성된 예상질문 → testset 후보 큐 → 사용자 승인 후 편입.
4. **피드백 루프**: 👎 답변 → testset 후보 + 원인 태그(검색/합성/인용/critical).
5. **Kill criteria 모니터**: §6 항목들을 query_traces 기반 대시보드로 —
   임계 관측 시 STATUS.md에 재심의 플래그 자동 기록.

## 종료 조건
- 전체 eval 회귀 무저하 + code/skill 질의 시나리오 통과 (출력 첨부)
- CI가 실제 커밋에서 증분 적재 1회 성공 (로그 첨부)
- STATUS.md 판정 섹션 작성 → 사용자 승인 → **v2 정식 운영 전환**
