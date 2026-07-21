# Phase 1 — RAG 코어

진입 조건: Phase 0 종료 판정 + 사용자 승인. 범위 밖: CAG·캐시 코드(Phase 2),
모호성 3종·FAQ·OOS·boost admin(Phase 3), code/skill 어댑터(Phase 4).

## 산출물 (순서대로 — DESIGN.md §8 Phase 1)

1. **어댑터 2종**: rule(docx — v1 파서 개량: 조 단위 Section 구조화, articles.py 사용,
   archive·민감문서 차단 로직 이식) + report(markdown 헤딩 단위).
2. **Contextual 적재**: chunk당 LLM 1콜(맥락 1~2문장 + keywords + category + 예상질문)
   → §3 스키마 저장 + **article_registry 동시 기록** (문서 단위 트랜잭션 replace).
   재적재 시 해시 미변경 chunk 스킵.
3. **hybrid 검색**: pgvector + pgroonga/TokenMecab + RRF, 메타데이터 필터 SQL 레벨
   (v1 hybrid_search_v3 RPC 이식·개량). 원 쿼리 불가침 + 병렬 multi-query(확장은 dense만).
4. **리랭커 이식**: v1 nexus_reranker(Flash-Lite listwise) + helper_health 회로 가시화.
5. **섹션 계약 합성**: v1 prompts 이식 (질문 확인→핵심 결론→📋 사규 기준→⚖️ 징계 기준→
   권장 행동→[참조]→칩). Gemini primary / Claude fallback.
6. **§5 조항 검증기**: 답변에서 (문서명, 조항번호) 추출(articles.py) → article_registry
   대조 → 통과/제거·재합성/차단·강등. 결정론 — LLM 판단 금지.
7. **답변 수준 인용 스코어러**: §5 추출기+registry 재사용, retrieve 비경유 경로도 채점
   가능하게(Phase 2 CAG 채점의 계측기). golden testset 구축 — 카테고리 층화 최소 50문항
   + critical·유사 조항 혼동·중간부 문서 케이스 필수.
8. **critical 게이트 + pii_filter + 핫라인 이식** (v1 소형 모듈): 어떤 형태의 사용자
   노출도 이 항목 완료 전 금지.
9. **최소 UI** (Streamlit, DESIGN.md 디자인 시스템 준수, 빌더 본인 전용 표시).
10. **eval 베이스라인 확정**: 검색 수준 + 인용 수준 모두 — 이것이 Phase 2 G3의 비교 기준.

## 종료 조건
- golden testset 전 문항이 파이프라인을 완주하고 인용 스코어러 점수 기록 (출력 첨부)
- critical 케이스가 핫라인 우선 경로로 빠지는 것 확인 (출력 첨부)
- §5 검증기 오탐/미탐 표본 점검 — G2 분모 독립화: 문서별 무작위 1개 장(章)
  인간 표본 감사 결과를 사용자에게 요청 [사용자 액션]
- STATUS.md 판정 섹션 작성 → 사용자 승인 대기
