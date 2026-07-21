# Phase 0 — 기반+측정 (타임박스 2주)

범위: 이 문서에 적힌 것만. Phase 1 이후 코드(리랭커·합성·UI·CAG)는 한 줄도 금지.

## 산출물 (순서대로)

1. **레포 골격**
   - `compass_engine/` 뼈대: 스테이지 typed 입출력 dict + trace 레코드 계약만.
     추상화 상한 = DESIGN.md §2 (retrieve 스테이지만 교체형 인터페이스). 초과 금지.
   - `compass_engine/articles.py`: 조항 정규화 단일 함수.
     "제N조", "제N조의M", 부칙, 별표, 삭제조항 지원. 단위 테스트 필수 —
     "제3조의2"가 "제3조"로 붕괴하면 실패해야 한다 (v1 파서의 실제 결함).

2. **스키마** (`db/schema.sql` + 마이그레이션 파일 — 실행은 [사용자 액션])
   - DESIGN.md §3 전체: documents/sections/chunks(부모-자식), article_registry,
     boost_rules(active ⇒ eval_run_id NOT NULL + 해당 run 판정=passed 제약),
     pinned_citations, query_traces, faq_cache·synonym_dictionary·critical_keywords·
     hotline_config(v1 이식), source_type별 RLS 정책 명시.
   - RLS 검증 스크립트: anon 키로 각 테이블 SELECT 시 "에러 없이 빈 배열" 함정 탐지.

3. **검색 수준 eval 하니스**: v1 레포(nexus_ai)의 eval/를 새 스키마에 맞게 이식.
   인용 수준 스코어러는 Phase 1 — 만들지 마라.

4. **측정 절차 안내**: 사용자에게 tools/gate1-measurement-kit.sql 실행(v1 Supabase
   대상)과 STATUS.md G1 표 기입을 안내. 숫자가 오면 tools/cost_calculator.py에
   반영해 G1 판정을 STATUS.md에 기록.

## 종료 조건
- 스키마가 사용자 수동 실행으로 Supabase에 적용 + RLS 검증 스크립트 통과
- articles.py 단위 테스트 통과 (실행 출력 첨부)
- 검색 eval 하니스 더미 데이터 1회 완주 (실행 출력 첨부)
- G1 판정 기록 완료
- STATUS.md Phase 0 판정 섹션 작성 → 사용자 승인 대기
