# STATUS.md — 진행 상태 (Claude Code가 갱신)

**현재 Phase: 1** (2026-07-22 사용자 승인으로 Phase 0 → 1 전환)
(Phase 전환은 종료 판정 + 사용자 승인 후에만. CLAUDE.md Part 0 참조)

---

## Phase 1 체크리스트 (지시서: docs/phases/phase-1.md · 순서 조정: 스코어러 앞순위)

조정 근거(2026-07-22 사용자 지시): 인용 스코어러(원 7번)를 최선두로 —
3.6 Flash 품질 판정(synth_bench 소급 채점)을 Phase 1 초반에 확정.
ADR-8/8a 반영: article_registry 테이블 없음 → 파생 원장(registry.py) 대조,
contextual 적재(원 2번)는 ctx_* 백필로 이미 대체됨.

- [x] ⓪ 답변 수준 인용 스코어러 완성 + 3.6 Flash 품질 판정 (2026-07-22):
      compass_engine/citations.py (§5 추출·대조 코어 — articles.find_article_refs
      신설 재사용, 파생 원장 verify, 접두어 생략 제목 해석기) + eval/
      score_synth_bench.py. 오프라인 테스트 6개 포함 전체 32 passed.
      **소급 채점 결과 (fixtures 16, 동일 조건)**:
      | | 인용쌍 | ok(검증) | article_missing | doc_missing | unattributed | 위조 포함 답변 |
      |---|---|---|---|---|---|---|
      | A 3.5-flash | 62 | 12 (19.4%) | 42 | 3 | 5 | 9/16 |
      | B 3.6-flash | 45 | **15 (33.3%)** | 30 | **0** | **0** | 9/16 |
      **판정: 3.6 Flash 인용 무결성 non-inferiority 성립 — 오히려 우위**
      (검증률 +13.9pp·문서 위조 0·미귀속 0·인용 더 선별적). 효율 우위(토큰
      −18.4%·지연 −42% p50)와 결합 시 합성 모델 교체 후보로 적격. 교체 확정은
      사용자 결정 + 정식 합성 A/B(골든셋) 후.
      ⚠️ 절대 수치 해석 한계: ① 벤치 프롬프트가 "(문서명, 제N조)" 형식을
      강제 — 조 구조가 아닌 문서(예: 대외출강 지침, 청크에 제3조·부칙만)에
      제N조 인용을 유도 → 양쪽 공통의 article_missing 폭증(표본 점검 확인).
      상대 비교만 유효. ② 원장 재현율 = G2 인간 표본 감사 필요 재확인
      (docs_with_articles 98/101, 조 표기 희박 문서 존재)
- [x] ⑦ golden testset 52문항 구축·검증 (별도 항목 ⓪ 아래 2026-07-22 완료 —
      eval/golden.yaml + tools/validate_golden.py PASS 52/52. 층화: critical 8/
      standard 14/confusion 6/mid_corpus 8/paraphrase 10/negative 6.
      기대 인용은 원장 실재 표기 수준, negative 는 답변 수준 판정 기준 명시)
- [~] ③ (부분) keyword leg 복원 — pgroonga_query.py 이식(토큰+조사+OR),
      golden 검색 베이스라인 41/52·R 0.875·양 leg 융합(0.0328) 확인.
      잔여: 병렬 multi-query·synonym 확장·negative 임계
- [x] 3.6 Flash 정식 A/B (golden 52, 채택 판정 — 아래 표) + 스코어러
      doc-level 채점 수정(제목 출현 기준 — 조항 앵커 아티팩트 교정)
- [~] ① 어댑터 2종 + ② 재적재 훅 — **ADR-8 로 보류** (컷오버 전 v2 는
      SELECT 전용, 적재는 v1 parser/ingest 가 계속 담당. 컷오버 국면에서 재개)
- [x] ④ 리랭커 이식 (2026-07-22) — compass_engine/reranker.py (listwise·JSON,
      env NEXUS_RERANK_MODEL 기본 3.5-flash-lite + thinking_level minimal 확정분,
      fail-open+지연 계측) + V1RpcRetriever 주입 배선(pool 15→top3).
      **golden 52 측정: 41/52 → 42/52, avg P 0.449→0.590(+0.141),
      avg R 0.875→0.904** (confusion P 0.56→0.89·R 1.00, paraphrase 7→8/10).
      rerank 지연 p50 667ms·실패 0/53. 오프라인 배선 테스트 2개(전체 34 passed)
- [x] ⑤ 섹션 계약 합성 (2026-07-22) — compass_engine/synthesis.py: v1 섹션
      계약 미러 + golden 인용 원칙 + Gemini(3.6 확정) primary/Claude fallback
      (주입형·no-silent). **golden 52 end-to-end 성적표 (동결 베이스라인 대비)**:
      재현율 39/51 76.5%(+7.9pp) · 위조 2/52(기준 ≤3, 베이스라인 3보다 개선) ·
      negative 6/6 · 섹션 계약 위반 0 · fallback 0 · 문항 실패 0 → **통과**.
      과정 기록: 1차는 [참조: <문서명> <조항>] 템플릿이 조항 창작 유도(위조
      13/52)로 불합격 → 원인 특정·템플릿 수정 후 재측정. 2차는 네트워크
      단건 오류 전파로 무효 → 하니스에 문항별 재시도+실패기록 내성 추가.
      negative 1건은 채점 마커 갭("확인할 수 없" 변형 누락) — 교정·재채점
- [x] ⑥ §5 조항 검증기 (2026-07-22) — compass_engine/verify.py: 스펙 그대로
      (ok→pass / article_missing→degrade(강등 채택) / document_missing→block),
      ⓪ 추출·대조 코어와 동일 모듈 재사용(드리프트 방지), 간이 confidence,
      섹션 계약 검사 통합. 테스트 5개(전체 43 passed).
      **3차 러닝 52답변 소급: pass 50 / degrade 2 / block 0 — 위조 2건
      (g04·g10)을 정확히 강등 포착** (서열 1위의 코드 보증 실측)
- [x] ⑧ critical 게이트 + pii_filter + 핫라인 이식 (2026-07-22 — H 보충 기준
      '무수정 이식' 경로, 착수 플래그 후 진행):
      · compass_engine/v1port/: pii_filter·critical_mode·nexus_critical_classifier
        **3개 모듈 byte-identical 복사** (diff 무출력 증명). shim 2개만 신규
        (config 발췌 복사·_gen_claude anthropic 재현 — 동작 보존 글루)
      · compass_engine/intake.py: v1 ask() 실측 순서 미러
        (mask_pii → load_keywords → detect(원문)→detect(masked))
      · **결과 동등성: golden critical 8문항 v1 원본 vs v2 이식본 —
        (triggered, kind, matched) 8/8 완전 일치** (동일 live keywords).
        미발동 4건(g03·g04·g06·g07)도 v1 과 동일 미발동 = 충실 이식
      · **경로 동일 증적(사용자 요구)**: 실행 타임스탬프 로그 —
        ① intake critical 판정(1.6s 시점) → ② retrieve → ③ synthesize →
        ④ enforce_structure(4단+핫라인 박스). **판정이 검색·합성 이전 발동.**
        v1 실체 명시: v1 도 critical 시 검색·합성을 생략하지 않고(안전 카테고리
        확장+critical 프롬프트) 판정만 선행 — v2 동일. v1 의 FAQ/OOS/askback
        fast-path 차단(not triggered 가드)은 해당 fast-path 가 생기는 Phase 3
        에서 같은 가드로 이식 (현 v2 엔 차단할 fast-path 없음)
      · IntakeResult 에 critical_kind 필드 추가(additive — 핫라인 safety/
        harassment 분기 운반용, DESIGN §2 intake 판정 스펙 내)
      · 오프라인 회귀 5개(floor·benign·incident override·4단·intake) —
        전체 48 passed. LLM fallback(classifier)은 양 레포 동일 조건 동일
        거동(키 부재 시 fail-open) — v1 과 등가
- [x] ⑨ 최소 UI (2026-07-22) — app.py: Streamlit 빌더 전용 프리뷰
      (V2 BUILDER PREVIEW 배지 명시), Warm Editorial 팔레트 축약 이식.
      정본 파이프라인 배선: intake→retrieve(v4-ctx+rerank+이웃)→synthesize→
      verify — **verify block 시 답변 미표출**(서열 1위), degrade 시 강등 칩,
      critical 시 배너+enforce_structure(4단+핫라인). trace 는 로컬 stderr
      (ADR-8 DB 쓰기 금지). 검증: AppTest 헤드리스 — 초기 렌더 + 라이브
      1문항 end-to-end(섹션 계약 답변·verify 칩 렌더·예외 0, action=pass)
- [ ] ⑩ eval 베이스라인 확정 (검색+인용)

### 등재 안건 (구현 금지 — 심의 후 착수)
- **critical 검출 커버리지 개선 (키워드 사전 확장 또는 분류기 활성화)**
  · 분류: **규율 H 심의 대상 (critical 동작 변경)**
  · 착수 시점: **컷오버 이후 v1·v2 공통 개선으로**
  · 배경: ⑧ 동등성 확인에서 golden critical 8문항 중 4건(g03 익명 비위
    신고 / g04 고객 쓰러짐 / g06 개인정보 유출 표현 변형 / g07 신고 채널)이
    v1·v2 공히 keyword 레벨 미발동 — 충실 이식의 증거인 동시에 v1 검출
    커버리지의 실측 갭. LLM fallback(classifier) 활성화 여부·키워드 확장안은
    심의에서 결정 (2026-07-22 사용자 지시로 등재만)

---

## Phase 0 체크리스트 (지시서: docs/phases/phase-0.md · 타임박스 2주)

- [x] compass_engine/ 패키지 뼈대 — stages.py: 5스테이지 TypedDict + TraceRecord + Retriever 프로토콜(유일 교체형, 상한 준수). CAG 구현 없음(G1 미통과 반영)
- [x] compass_engine/articles.py — 조항 정규화 단일 함수(제N조/조의M/부칙/별표/삭제) + 단위 테스트 19/19 통과 (조의2 붕괴 회귀 테스트 포함, 실행 출력 커밋 메시지 첨부)
- [~] ~~db/schema.sql + 마이그레이션 + RLS 검증~~ — **ADR-8(DB 불변)로 폐기**
      (2026-07-21 사용자 결정: 신규 프로젝트·마이그레이션·SQL Editor 작업 없음.
      산출물은 커밋 이력에만 남김). 대체 항목 ↓
- [x] [사용자 액션] v1 스키마 리플렉션 — **R1·R2 회신·확정 완료** (2026-07-22):
      R2 = v3 시그니처 잠정 계약 완전 일치·v4_ctx 실재. R1 = 10테이블 전수 —
      v2 사용 전 컬럼 물리 실재 + ctx_prefix/ctx_embedding 물리 확인.
      부수 발견: chunk_incident_nodes 물리 부재인데 v1 retriever.py:1595
      .select() 에 잔존(42703 소지) — v1 수정 금지, 보고만
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
      (예외 = ADR-8a 백필의 ctx_* 2컬럼)

### ADR-8a 완화 후속 (2026-07-21 지시)
- [x] ① small-to-big 근사 — compass_engine/neighbors.py: hit 청크에 chunk_idx
      ±2 이웃 런타임 결합(DB 변경 없음), V1RpcRetriever 기본 on.
      오프라인 테스트 4개(창 결합·경계·타문서 비오염·fail-open) 통과
- [x] ② additive SQL 작성 — db/additive/20260721_ctx_columns_and_v4.sql
      (ctx_prefix·ctx_embedding + HNSW + v4 RPC, 1파일 1회 실행).
      v1 무영향 전수 grep 증거 → docs/v1-schema-reflection.md 기록
- [x] [사용자 액션] 위 SQL 실행 완료 — 아래 별도 항목 및 R1 물리 컬럼 확인으로 이중 확증
- [x] ③ 백필 스크립트 — tools/ctx_backfill.py (문서별 맥락 1~2문장 생성 +
      ctx_embedding 기록, ctx_* 2컬럼만 쓰기·이어하기·실패 요약).
      실행은 컬럼 추가 후 [사용자 액션 또는 creds 제공 시 Claude 실행]
- [x] ④ eval A/B — eval/run.py --v4-ctx·--ab (v1 vs contextual, 개선폭 Δ 출력)
- [x] [사용자 액션] additive SQL v1 프로젝트 실행 완료 ("Success. No rows returned")
- [x] ③실행 — 백필 라이브 완료: **성공 628 / 실패 0 / 대상 628** (active 문서 101개)
- [x] ④실행 — A/B 라이브 (fixtures 16, top_k=3, 2026-07-21):
      **v3(A) 4/16 pass → v4-ctx(B) 8/16 pass (Δ+4)** ·
      avg P 0.208→0.354 (Δ+0.146) · avg R 0.281→0.594 (Δ+0.312) ·
      flips: q05·q06·q11·q12·q16 ❌→✅, q10 ✅→❌
      ⚠️ 해석 한계(계측 조건):
      ① 두 백엔드 모두 keyword leg 무효 — 원문을 pgroonga OR 쿼리로 변환하는
        v1 의 nexus_build_pgroonga_query 미이식(양쪽 best=0.0164=vector 단일 leg).
        따라서 **A 는 v1 운영 성능을 대표하지 않는다** — 이 Δ 는 "동일 래퍼에서
        embedding vs ctx_embedding 컬럼 비교"로만 유효 (쿼리 빌더 이식은 Phase 1)
      ② q09·q10 negative 실패는 임계치 없는 하니스 아티팩트(v4 는 항상 top-3 반환,
        점수 컷 없음) — contextual 회귀가 아니라 negative 판정 설계 보완 필요
      결론: 동일 조건 비교에서 ctx_embedding 명확 우위 → contextual 백필 유지 근거.
      "v1 대비 개선"으로 확대해석 금지
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

### Gemini 신모델(2026-07-21 발표) 적용 검토 — 지시 4건 처리
1. **model ID 확인 (API 실조회, 56종)**: `gemini-3.5-flash-lite` ✅ ·
   `gemini-3.6-flash` ✅ · `gemini-2.5-flash-lite`(현행) ✅ 실재.
   ⚠️ 3.5 계열은 구식 `thinking_budget` 파라미터를 400 으로 거부 —
   **`thinking_level`("minimal") 사용** (단건 프로브 4종으로 확정).
2. **리랭커 A/B (eval/rerank_ab.py — pool 15 v4-ctx → listwise → top3,
   fixtures 16, 양쪽 17콜 실패 0)**:
   | | pass | avg P | avg R | p50 | p95 |
   |---|---|---|---|---|---|
   | A 2.5-flash-lite | 9/16 | 0.333 | 0.656 | 567ms | 676ms |
   | B 3.5-flash-lite(minimal) | **11/16** | **0.396** | **0.781** | 622ms | 693ms |
   Δ pass +2 (q11·q12 ❌→✅, 회귀 0) · R +0.125 · 지연 +55ms(p50)/+17ms(p95).
   **판정: B 우위 → v2 리랭커 기본값 = gemini-3.5-flash-lite + thinking_level
   minimal 로 확정** (적용 = Phase 1 리랭커 이식 시 env NEXUS_RERANK_MODEL —
   코드 무수정 원칙, v1 은 불변).
   ※ 첫 실행은 B 17콜 전패(400)로 무효 판정 → 원인 특정 후 재실행한 결과임.
3. **[예약 — Phase 1 종료 후] 합성 모델 A/B**: 현행 vs `gemini-3.6-flash` —
   답변 수준 인용 스코어러 완성 후 품질·출력토큰·지연 3축 비교.
   **그 전까지 v1·v2 합성 모델 교체 금지** (계측기 없는 교체 금지 규율).
4. **Flash Cyber 기각**: 용도 불일치(보안 특화)·접근 제한 — API 모델 리스트
   56종에 cyber 계열 부재로 방증. 재검토 계획 없음.

### 3.6 Flash 선행 벤치 (2026-07-22 지시 — 합성 모델 교체 금지 규율 유지)
- 조건: fixtures 16 × 양 모델, 동일 컨텍스트(v4-ctx top3+이웃결합)·동일 프롬프트·
  기본 thinking, stream·max_output_tokens 4096. **32콜 전부 finish=STOP 완결 확인.**
- 결과 (A=gemini-3.5-flash 현행 / B=gemini-3.6-flash):
  | | 출력 토큰 평균 | TTFT p50 | TTFT p95 | 총 생성 p50 | p95 |
  |---|---|---|---|---|---|
  | A | 363 | 7620ms | 10168ms | 9809ms | 12545ms |
  | B | **296 (−18.4%)** | **4605ms** | 7705ms | **5728ms (−42%)** | 9599ms (−23%) |
  → **광고("출력 ~17% 감소·지연 감소") 이 워크로드에서 재현됨.** 품질 판정은
  아님 — 채택 여부는 인용 스코어러 소급 채점 후 (교체 금지 규율 유지).
- 저장본: eval/results/synth_bench_20260722T015757.json — 답변 전문+컨텍스트+
  프롬프트+계측 포함, **Phase 1 스코어러로 소급 채점 가능 (재실행 불요)**.
- 계측 이력(정직 기록): 1차(stream)·2차(non-stream)는 max_output_tokens=1024
  에서 **기본 thinking 이 출력 예산을 소모해 MAX_TOKENS 절단**(11/16·10/16)
  → 무효 폐기. 중간에 세운 "프록시 SSE 유실" 가설은 **오진으로 철회**
  (finish_reason 실측으로 반증). 상한 4096 3차만 유효본.
  ※ TTFT 절대값은 프록시 경유 환경 수치 — A/B 상대 비교로만 사용,
  절대 지연은 배포 환경에서 재확인.

### Phase 0 종료 판정 (ADR-8 기준으로 교체: 스키마 리플렉션 문서 +
### 파생 원장 빌더 + RPC 래퍼 리트리버 + eval 완주)
- 판정: **완료 — 종료 조건 4/4 충족. 사용자 승인 대기**
- 근거:
  ① 파생 원장 빌더 ✅ (tests/test_registry.py 3 passed — 조의2 보존·3분기 verify)
  ② RPC 래퍼 리트리버 ✅ (V1RpcRetriever — 라이브 검증까지 완료: v4-ctx A/B·
    리랭커 A/B·synth 벤치가 전부 이 래퍼로 실측됨)
  ③ eval 완주 ✅ (더미 EXIT=0 + 라이브 --ab 실측 2종)
  ④ v1 스키마 리플렉션 문서 ✅ (R1·R2 확정 — v2 사용 전 컬럼 물리 실재,
    v3 시그니처 일치, ctx_* 물리 확인)
  (+) 타임박스 2주 내 완료. Phase 밖 선구현 없음(CAG 0줄).
- 사용자 승인: **✅ 승인 (2026-07-22)** — Phase 1 전환 완료

---

## Phase 1~4
각 Phase 진입 시 Claude Code가 해당 지시서(docs/phases/)를 기준으로
이 파일에 체크리스트를 생성한다.

### 3.6 Flash 정식 A/B — 합성 모델 채택 판정 (golden 52, 2026-07-22)
| | A gemini-3.5-flash(현행) | B gemini-3.6-flash |
|---|---|---|
| 기대 인용 재현율 | 36/51 (70.6%) | 35/51 (68.6%) |
| **위조 인용 답변** | 6/52 | **3/52 (절반)** |
| negative pass | 6/6 | 6/6 |
| 비정상 finish | 4 | **1** |
| 출력 토큰 평균 | 304 | 307 (동등) |
| TTFT p50 | 8085ms | **6778ms (−16%)** |
| 총생성 p50 / p95 | 9445 / 15428ms | **8137 / 13487ms (−14%/−13%)** |
**판정: gemini-3.6-flash 채택 — 2026-07-22 사용자 확정.**
- **v2**: 합성 기본값 = gemini-3.6-flash 즉시 확정. **답변 수준 베이스라인은
  golden_ab_20260722T105320.json 의 B(3.6) 열로 동결** — 이후 합성·프롬프트·
  검색 변경은 이 베이스라인 대비 Δ 로 판정.
- **v1**: 조건부 교체 — **[사용자 액션] 실행 확인 완료 (2026-07-22 11:49)**:
  Reboot 후 전 호출 model=gemini-3.6-flash · 4문항(징계/응급환자/비권한자/
  괴롭힘) 전부 정상 · critical 게이트 무손상(②④ ALERT+핫라인 우선 발동) ·
  실측 합성 30.4→10.7s(−65%)/23.7→15.5s(−34%) · ③은 중대재해 지침 인용으로
  오히려 개선. **3일 관찰 타이머 기점 2026-07-22 11:49 — 2026-07-25 사용자
  관찰 SQL 회신 시 교체 전 구간과 비교해 최종 판정 기록 예정.**
  이상 신호 시 env 1줄 롤백(`gemini-3.5-flash`) + Reboot.
  ※ 배포 교훈(재기동 전 미반영 = settings() lru_cache) → docs/deploy-notes.md
- 비용 기록: 3.6-flash 출력 단가 3배 — 당사 규모(일 ~24질의)에선 월 수천 원
  수준 증가. 채택 판단에 영향 없음 (기록만).
※ 계측 정직 기록: 1차 채점은 doc-level 기대를 조항 앵커 추출기로 채점해
7.8%/5.9% 로 붕괴 — 표본 점검으로 아티팩트 확인 후 제목 출현 기준으로
수정·재채점한 값이 위 표. 저장본: eval/results/golden_ab_20260722T105320.json

**Phase 1 순서 조정 (2026-07-22 사용자 지시)**: 착수 시 **답변 수준 인용
스코어러를 앞순위로 당긴다** (DESIGN §8 원 순서에서는 후반부) — 목적:
3.6 Flash 품질 판정(저장된 synth_bench 소급 채점)을 Phase 1 초반에 확정하고,
이후 리랭커(3.5-flash-lite minimal)·합성 모델 결정을 같은 계측기로 잇기 위함.
전제인 articles.py·파생 원장(registry)은 Phase 0 에서 이미 완성됨.

## 작업 로그 (최신이 위)
- 2026-07-22 ⑨ 최소 UI 완료(AppTest 초기+라이브 검증) + critical 커버리지 안건 등재(H 심의·컷오버 후·구현 금지). 잔여 = ⑩ 베이스라인 확정 + ③ 잔여.
- 2026-07-22 ⑧ critical 이식 완료: 3모듈 byte-identical + 동등성 8/8 + 경로 순서 증적(판정→검색→합성→4단핫라인). IntakeResult.critical_kind additive. 48 passed.
- 2026-07-22 ⑤ 통과(재현율 76.5%·위조 2·negative 6/6) + ⑥ §5 검증기 완성(소급: 위조 2건 정확 강등). 다음 = ⑧ critical 이식(H 보충 기준: 무수정 이식 → 착수 플래그).
- 2026-07-22 v1 3.6 교체 실행 확인(사용자): 4문항 정상·critical 무손상·합성 −65%/−34%. 3일 관찰 시작(~7/25). lru_cache 배포 교훈 → docs/deploy-notes.md.
- 2026-07-22 ④ 리랭커 이식(확정 모델) + golden 측정: P +0.141·R +0.029·pass 42/52. 검색 수준 현행 최고 구성 = v4-ctx+OR쿼리+rerank.
- 2026-07-22 ① v1 핫픽스 3층 검증 마감(사용자 실행 확인: 4문항 정상·L1_RPC 136·42703 없음·critical 무손상) — 종결. ② 3.6-flash 채택 확정: v2 즉시(베이스라인 동결), v1 조건부([사용자 액션]+3일 관찰). ①②적재는 ADR-8 보류 → 다음 = ④ 리랭커 이식.
- 2026-07-22 3.6 정식 A/B(golden 52): 재현율 70.6%↔68.6%(non-inferior)·위조 6→3·지연 −14%·finish 안정 → 채택 권고. 1차 채점 아티팩트(조항 앵커) 수정 이력 명기.
- 2026-07-22 Phase 1 ⓪ 완료: 인용 스코어러(citations.py+score CLI, 32 passed) → 3.6 품질 판정 = non-inferiority 우위(검증률 19.4%→33.3%, dm·un 0). 절대치는 벤치 프롬프트 유도 한계 명기. 스코어러 결함 2건(직접 인용형 우선순위·접두어 제목) 표본 점검으로 발견·수정.
- 2026-07-22 Phase 0 종료 승인(사용자) → Phase 1 전환. 체크리스트 생성(스코어러 ⓪ 앞순위). 착수: 인용 스코어러.
- 2026-07-22 리플렉션 R1 회신 반영 → 리플렉션 확정. Phase 0 종료 조건 4/4 충족 — 판정 작성, 사용자 승인 대기. (부수: chunk_incident_nodes 물리 부재 + v1 retriever.py:1595 잔존 select 관찰 보고)
- 2026-07-22 리플렉션 R2(RPC) 회신 반영: v3 계약 일치·v4_ctx 실재 확정. R1(컬럼 덤프) 대기.
- 2026-07-22 3.6 Flash 선행 벤치(유효 3차): 토큰 −18.4%·총생성 p50 −42% — 광고 재현. 답변 전문 저장(소급 채점용). 1·2차는 thinking 예산 절단으로 무효 폐기(SSE 유실 가설 철회). Phase 1 은 인용 스코어러 앞순위로 조정.
- 2026-07-21 Gemini 신모델 검토: ID 실확인(3.5-flash-lite·3.6-flash), 리랭커 A/B → 3.5-flash-lite(minimal) 우위(pass 9→11, R +0.125, 지연 +55ms) → v2 기본값 확정(Phase 1 적용). 합성 A/B 는 Phase 1 후 예약, Flash Cyber 기각.
- 2026-07-21 백필 628/628 성공(실패 0) + A/B 라이브: v3 4/16 → v4-ctx 8/16 (Δ+4, R +0.312). 캐비앗: keyword leg 미이식·negative 임계치 — Phase 1 과제.
- 2026-07-21 ADR-8a(완화): 이웃 결합(즉시)+additive SQL/v4 RPC 작성+백필 스크립트+eval A/B 하니스. 남은 것=[사용자 액션] SQL 실행→백필→A/B 숫자.
- 2026-07-21 전략 변경(사용자): DB 재설계 취소 → ADR-8(DB 불변·SELECT 전용). schema.sql/마이그레이션/rls_verify 폐기, 스키마 리플렉션 킷 + 파생 원장 빌더 + v1 RPC 래퍼 리트리버로 대체.
- 2026-07-21 Phase 0 항목 2·3(작성분)·4 완료: schema.sql+마이그레이션 0001, rls_verify.py(canary), eval 하니스 이식(더미 완주 EXIT=0). 남은 것 = [사용자 액션] 마이그레이션 실행→RLS 통과.
- 2026-07-21 Phase 0 항목 1 완료: compass_engine 뼈대 + articles.py (pytest 19 passed).
- 2026-07-21 G1 실측값 기입(사용자 회신) + cost_calculator 재현 실행 → 51.4x 미통과 확인. rule 트랙 RAG 확정.
- 2026-07-21 스타터 번들 생성. Phase 0 대기.
