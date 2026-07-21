# STATUS.md — 진행 상태 (Claude Code가 갱신)

**현재 Phase: 0**
(Phase 전환은 종료 판정 + 사용자 승인 후에만. CLAUDE.md Part 0 참조)

---

## Phase 0 체크리스트 (지시서: docs/phases/phase-0.md · 타임박스 2주)

- [x] compass_engine/ 패키지 뼈대 — stages.py: 5스테이지 TypedDict + TraceRecord + Retriever 프로토콜(유일 교체형, 상한 준수). CAG 구현 없음(G1 미통과 반영)
- [x] compass_engine/articles.py — 조항 정규화 단일 함수(제N조/조의M/부칙/별표/삭제) + 단위 테스트 19/19 통과 (조의2 붕괴 회귀 테스트 포함, 실행 출력 커밋 메시지 첨부)
- [~] ~~db/schema.sql + 마이그레이션 + RLS 검증~~ — **ADR-8(DB 불변)로 폐기**
      (2026-07-21 사용자 결정: 신규 프로젝트·마이그레이션·SQL Editor 작업 없음.
      산출물은 커밋 이력에만 남김). 대체 항목 ↓
- [ ] [사용자 액션] v1 스키마 리플렉션: tools/schema_reflect.sql (R1·R2) 을
      **v1** SQL Editor 에서 실행 → 결과 회신 → docs/v1-schema-reflection.md 확정
      (실행 전까지 v2 는 문서의 "잠정 계약(코드 근거)" 컬럼만 사용)
- [x] §5 파생 원장 빌더 — compass_engine/registry.py: nexus_chunks.text 를
      articles.py 로 재추출해 (document_id, canonical) 메모리 원장 구축.
      v1 article_no 컬럼 사용 금지(조의N 붕괴) 준수 — 컬럼 붕괴값이 있어도
      text 재추출로 조의2 보존되는 회귀 테스트 포함. tests 3개 통과
- [x] v1 RPC 래퍼 리트리버 — compass_engine/v1_retriever.py:
      nexus_hybrid_search_v3_pgroonga 호출(payload 는 v1 호출부 미러),
      Retriever 프로토콜 구현. eval/run.py --v1-rpc 로 연결 (SELECT/RPC 전용)
- [x] 검색 수준 eval 하니스 이식 + 더미 1회 완주 — Retriever 프로토콜 기반
      (eval/runner.py·run.py·dummy_retriever.py, fixtures 16개). EXIT=0,
      16/16 실행 (12 pass — 더미 기준, 품질 주장 아님)
- 기록 정책(ADR-8): query_traces·eval_runs DB 기록은 당분간 로컬 파일/로그로
      대체 (eval 결과 = eval/results/*.json). **DB 쓰기 금지**
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

### Phase 0 종료 판정 (ADR-8 기준으로 교체: 스키마 리플렉션 문서 +
### 파생 원장 빌더 + RPC 래퍼 리트리버 + eval 완주)
- 판정: **미완 — [사용자 액션] 1건(스키마 리플렉션 덤프)에 블록**
  (Claude 측 작업은 전부 완료)
- 근거:
  ① 파생 원장 빌더 ✅ (tests/test_registry.py 3 passed — 조의2 보존·3분기 verify)
  ② RPC 래퍼 리트리버 ✅ (V1RpcRetriever, eval --v1-rpc 연결. 라이브 호출은
    creds 필요 — 코드·프로토콜 정합은 오프라인 검증)
  ③ eval 완주 ✅ (더미 EXIT=0, 16 fixtures)
  ④ v1 스키마 리플렉션 문서 ⏸ — **[사용자 액션] schema_reflect.sql 덤프 회신
    → docs/v1-schema-reflection.md 확정 시 충족** (잠정 계약은 기록됨)
- 사용자 승인: _대기 (④ 완료 후 판정 확정 요청 예정)_

---

## Phase 1~4
각 Phase 진입 시 Claude Code가 해당 지시서(docs/phases/)를 기준으로
이 파일에 체크리스트를 생성한다.

## 작업 로그 (최신이 위)
- 2026-07-21 전략 변경(사용자): DB 재설계 취소 → ADR-8(DB 불변·SELECT 전용). schema.sql/마이그레이션/rls_verify 폐기, 스키마 리플렉션 킷 + 파생 원장 빌더 + v1 RPC 래퍼 리트리버로 대체.
- 2026-07-21 Phase 0 항목 2·3(작성분)·4 완료: schema.sql+마이그레이션 0001, rls_verify.py(canary), eval 하니스 이식(더미 완주 EXIT=0). 남은 것 = [사용자 액션] 마이그레이션 실행→RLS 통과.
- 2026-07-21 Phase 0 항목 1 완료: compass_engine 뼈대 + articles.py (pytest 19 passed).
- 2026-07-21 G1 실측값 기입(사용자 회신) + cost_calculator 재현 실행 → 51.4x 미통과 확인. rule 트랙 RAG 확정.
- 2026-07-21 스타터 번들 생성. Phase 0 대기.
