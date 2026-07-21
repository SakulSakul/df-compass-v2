# Phase 2 — CAG 트랙 (게이트 판정)

진입 조건: Phase 1 승인 + G1 숫자 존재. G1이 이미 "미통과"면 이 Phase는
"rule 트랙 RAG 확정" 기록만 남기고 종료한다 — 그것도 유효한 결말이다 (DESIGN.md §8).

## 산출물 (순서대로)

1. **스파이크 (첫 작업, 반나절)**: Streamlit Cloud 단일 프로세스에서 백그라운드
   캐시 워밍 스레드가 실제 동작하는지 검증. 실패 시 §4-1을 "기동 시 warm + 강등 우선"
   으로 대체하고 결과를 DESIGN.md 개정 제안으로 보고.
2. **캐시 매니저 v2** (DESIGN.md §4 계약 5개 전부):
   - 워밍은 요청 경로 밖 · invalidation 자동화(적재 훅 + git SHA) ·
     miss 시 풀가격 전송 금지(즉시 RAG 강등 + 신뢰도 칩 표시) ·
     critical 지시 user-turn 배치(캐시 호환) · 문서 경계 + (doc_id, article_no)
     구조화 concat 포맷.
   - 재적재 훅 원자 단위: registry replace + 캐시 rebuild + faq_cache 무효화 +
     testset 영향 플래그 (§3 버전 스큐 방지).
3. **게이트 판정** (각각 독립, STATUS.md에 기록):
   - G1: cost_calculator.py 실측 판정 (이미 기록됨 — 재확인)
   - G2: registry 커버리지 — 분모는 인간 표본 감사 [사용자 액션]
   - G3: 동일 golden testset에서 CAG vs RAG(Phase 1 베이스라인) 인용 정확도
     non-inferiority — 인용 스코어러로 판정, critical·혼동·중간부 케이스 포함
4. **판정 결과 반영**: 3게이트 전부 통과 → rule 트랙 기본값 CAG-primary 전환
   (RAG 폴백 상시). 하나라도 미통과 → RAG 유지 확정, 사유를 DESIGN.md에 기록.

## 종료 조건
- 게이트 3종 판정 근거(숫자·출력)가 STATUS.md에 기록
- Kill criteria 모니터 항목(§6)이 query_traces 기반으로 관측 가능함을 확인
- STATUS.md 판정 섹션 작성 → 사용자 승인 대기

## v1 컷오버 (이 Phase 종료 시)
컷오버 조건 = 동일 testset non-inferiority + 관측 기간 2주 무사고.
충족 시 사용자에게 컷오버를 제안하되 실행(v1 중단)은 사용자 결정.
