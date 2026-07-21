# STATUS.md — 진행 상태 (Claude Code가 갱신)

**현재 Phase: 0**
(Phase 전환은 종료 판정 + 사용자 승인 후에만. CLAUDE.md Part 0 참조)

---

## Phase 0 체크리스트 (지시서: docs/phases/phase-0.md · 타임박스 2주)

- [ ] compass_engine/ 패키지 뼈대 (스테이지 typed dict + trace 계약, 상한 준수)
- [ ] compass_engine/articles.py — 조항 정규화 단일 함수 + 단위 테스트 통과
- [ ] db/schema.sql + 마이그레이션 파일 작성 (DESIGN.md §3 전체)
- [ ] [사용자 액션] 마이그레이션을 Supabase SQL Editor에서 실행 → 결과 회신
- [ ] RLS 검증 스크립트 작성·통과 (anon 빈 배열 함정 탐지)
- [ ] 검색 수준 eval 하니스 이식 (더미 데이터 1회 완주 출력 첨부)
- [ ] [사용자 액션] tools/gate1-measurement-kit.sql 실행 → 숫자 4개를 아래 G1 표에 기입
- [ ] tools/cost_calculator.py에 실측값 반영 → G1 판정 기록

### G1 실측값 (사용자 기입)

| 항목 | 값 |
|---|---|
| CORPUS_TOKENS (M1) | _미측정_ |
| DAILY_QUERIES (M3) | _미측정_ |
| CRITICAL_PCT (M4) | _미측정_ |
| RAG_CTX_TOKENS (M5) | _미측정_ |
| **G1 판정** | _미판정_ |

### Phase 0 종료 판정
- 판정: _미완_
- 근거: _(완료 시 Claude Code가 기입)_
- 사용자 승인: _대기_

---

## Phase 1~4
각 Phase 진입 시 Claude Code가 해당 지시서(docs/phases/)를 기준으로
이 파일에 체크리스트를 생성한다.

## 작업 로그 (최신이 위)
- 2026-07-21 스타터 번들 생성. Phase 0 대기.
