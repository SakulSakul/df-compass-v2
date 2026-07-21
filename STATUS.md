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
- [x] [사용자 액션] tools/gate1-measurement-kit.sql 실행 → 숫자 4개를 아래 G1 표에 기입 (2026-07-21 사용자 회신)
- [x] tools/cost_calculator.py에 실측값 반영 → G1 판정 기록 (계산기 실행 출력으로 51.4x 재현 확인)

### G1 실측값 (사용자 기입)

| 항목 | 값 |
|---|---|
| CORPUS_TOKENS (M1) | 284,849 (tokens_est_high, active 기준 — token_count 컬럼은 v1 미기입 상태였음) |
| DAILY_QUERIES (M3) | 24.1 (90일 평균, peak_day 602) |
| CRITICAL_PCT (M4) | 13.0% (Kill criteria 임계 30% 미만 — 문제없음) |
| RAG_CTX_TOKENS (M5) | 6,809 (p95 12,335) |
| **G1 판정** | **미통과 — RAG 유지.** CAG $109.37/월 vs RAG $2.13/월 = **51.4x** (상한 3x). storage 임대료 지배(일 $3.42 > RAG 월 비용). storage 제외 극단 가정에서도 질의당 3.2x로 상한 초과 — 질의량과 무관한 구조적 미통과 |

### 후속 결정 (2026-07-21, 사용자 확정)
- **rule 트랙 = RAG 확정.** phase-2.md 진입 조건에 따라 Phase 2 는 "rule 트랙 RAG 확정"
  기록만 남기고 종료 예정.
- Phase 0~1 에서 CAG 관련 코드는 조건부가 아니라 **영구 불필요**로 간주.
- 단 §2 엔진 계약의 retrieve 스테이지 교체형 인터페이스는 **유지** —
  미래 재심의 대비 롤백 구조이자 eval A/B 의 전제 (사용자 지시).

### Phase 0 종료 판정
- 판정: _미완_
- 근거: _(완료 시 Claude Code가 기입)_
- 사용자 승인: _대기_

---

## Phase 1~4
각 Phase 진입 시 Claude Code가 해당 지시서(docs/phases/)를 기준으로
이 파일에 체크리스트를 생성한다.

## 작업 로그 (최신이 위)
- 2026-07-21 G1 실측값 기입(사용자 회신) + cost_calculator 재현 실행 → 51.4x 미통과 확인. rule 트랙 RAG 확정.
- 2026-07-21 스타터 번들 생성. Phase 0 대기.
