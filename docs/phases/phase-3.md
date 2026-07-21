# Phase 3 — 품질 레이어

진입 조건: Phase 2 승인. 범위 밖: code/skill 어댑터·CI·자동화(Phase 4).

## 산출물

1. **intake 풀구성**: v1 모호성 3종(ambiguity 되묻기 · disambiguation 후보선택 ·
   multi_facet 분산 측정)을 단일 모호성 스테이지로 통합 이식 + FAQ cache
   (§4-2-1 신선도 규칙: 재적재 훅 무효화 + FAQ 답변도 §5 검증기 통과) + OOS router.
   대화 상태(되묻기→선택 2턴 흐름)를 엔진 계약에 명시 구현 (§3).
2. **대안 리랭커 A/B**: Cohere 등 API형 후보를 eval 하니스에서 Flash-Lite 대비 비교.
   교체는 eval 우위 + 데이터 반출 검토 통과 시에만.
3. **boost_rules admin**: shadow→active 2단계 — 규칙 추가 시 eval 회귀 자동 실행 →
   diff 표시 → 사용자 승인 시 active. DB 제약(passed run 필수)과 이중 방어.
4. **agentic 에스컬레이션**: 저신뢰 답변에서 옵트인 제공, 지연 고지, 반복 상한·
   타임아웃 명시, 결과도 §5 검증기 통과.

## 종료 조건
- eval 회귀 무저하 (베이스라인 대비 출력 첨부)
- 모호성 스테이지의 2턴 흐름이 실제 UI에서 동작 (수동 확인 시나리오 3건)
- STATUS.md 판정 섹션 작성 → 사용자 승인 대기
