# DF COMPASS v2 — 최종 설계서 v2.1

> 본 문서는 설계안 v1.1 + council 5인 심의 + 스택 사실검증 + **3인 축약 심의(미심의 결정부, 2026-07-21)** 를 통합한 단일 기준이다.
> 새 레포의 DESIGN.md로 그대로 사용 가능. 모든 하위 결정은 §0의 목적 서열에 종속된다.

---

## 0. 앱의 목적과 품질 서열 (모든 결정의 기준)

**목적: 신세계면세점 임직원이 사규를 "정확한 조항 근거와 함께" 확인하고, 사람이 개입해야
할 사안은 즉시 사람(핫라인·담당부서)에게 연결되는 도구.**

이 목적에서 도출되는 품질 서열 — 충돌 시 위가 이긴다:

1. **無인용 무결성**: 없는 조항 번호 생성 = 치명 결함. 실재하는 (문서, 조항)만 인용.
2. **Critical 안전**: 괴롭힘·임신·신고 등은 답변보다 핫라인 연결이 우선. 어떤 아키텍처
   경로에서도 이 게이트는 우회 불가.
3. **누락 최소**: 관련 조항이 있는데 "없다"고 답하지 않기 (v1의 만성 실패 모드).
4. **정직한 불확실성**: 신뢰도 낮으면 낮다고 표시하고 담당부서로 라우팅. 부서명 창작 금지.
5. **지연·비용**: 위 1~4를 훼손하지 않는 범위에서 최소화.

서열의 함의: "검색 품질을 올리는 개선"이라도 인용 무결성 검증을 약화시키면 기각.
비용 절감이라도 critical 경로를 건드리면 기각.

---

## 1. 아키텍처 결정 레코드 (ADR — 확정 사항)

| # | 결정 | 근거 (검증 경로) |
|---|---|---|
| ADR-1 | **엔진/UI 분리**: `compass_engine` 순수 패키지, Streamlit·eval CLI·(미래 MCP)가 동일 진입점 호출 | v1 chatbot.py 2,385줄 엉킴 + `retrieve_for_eval` 우회 함수의 존재 자체가 분리 실패 증거 |
| ADR-2 | **사규(rule) 트랙 = CAG-primary + RAG 폴백 상시**, 게이트 3종 통과 조건부 활성화 | council 5/5 수렴. 순수 CAG(RAG 삭제)는 기각 — Claude fallback이 Gemini 캐시를 상속 못하는 구조 제약 |
| ADR-3 | **코드·보고서·스킬 트랙 = 하이브리드 RAG** (pgvector + pgroonga/TokenMecab + RRF) | 성장형 코퍼스는 전체 열람 불가. v1 hybrid_search_v3가 검증된 구현 |
| ADR-4 | **API-first — 셀프호스트 임베딩/리랭커 기각** | Streamlit Cloud 무GPU + 솔로 운영 + 사규 데이터 제3사 반출 금지. Qwen3/BGE 계열은 레퍼런스로만 기록, eval A/B 슬롯으로 미래 대비 |
| ADR-5 | **규칙의 데이터화**: 부스트·고정 인용은 코드 상수가 아닌 DB 테이블 + eval 게이트 후 활성화(shadow→active) | v1 EMERGENCY_KEYWORDS·force-include 하드코딩의 두더지잡기 교훈. 단 DB 이전만으로는 두더지잡기가 장소만 바뀜 — eval 게이트가 본질 |
| ADR-6 | **eval-first**: 하니스가 첫 검색 코드보다 먼저. 모든 retrieval·prompt·규칙 변경은 eval diff 게이트 통과 후 반영 | v1은 eval이 phase 두 자릿수에 등장 — 그 전의 모든 튜닝이 미계측이었음 |
| ADR-7 | **CAG 채택 명분 = "솔로 빌더의 튜닝 표면적 축소"** (검색실패 0 아님) | council: 실패는 소멸이 아니라 이동(청크 누락→장문 주의 실패). 후자는 검출이 어려우므로 §5 검증기가 전제조건 |

---

## 2. 시스템 구성

```
질의
 │
 ▼
[1. intake]  PII 마스킹 → critical 분류(핫라인 우선, 아키텍처 무관 최상위 게이트)
 │           → OOS 라우팅 → FAQ 캐시 → 모호성 스테이지(bare토큰 되묻기·후보선택·multi-facet)
 ▼
[2. route]   intent → 트랙 결정 (기본: rule / 명시적일 때만 skill·code·report 추가)
 │
 ├─ rule 트랙 ──────────────► [3a. CAG answer]   Gemini explicit cache (전체 사규+프롬프트)
 │        └ (캐시 실패·Claude │                    캐시 miss 시 풀가격 재전송 금지 — 즉시 3b로 강등
 │           fallback·게이트  ▼
 │           미통과 시)────► [3b. RAG answer]   hybrid 검색(top-50) → rerank(top-8) → 합성
 │
 └─ code·report·skill 트랙 ─► [3b. RAG answer]  (동일 파이프라인, source_type 필터)
 │
 ▼
[4. verify]  조항 검증기(§5, 결정론) → 섹션 계약 검사 → 신뢰도 산출
 │           저신뢰 → agentic search 에스컬레이션(옵트인) 또는 담당부서 라우팅
 ▼
[5. render]  고정 섹션 + 인용 + 카테고리/신뢰도 칩 + grounded 후속질문 (스트리밍)
 │
 ▼
[trace]      전 스테이지 기록 (query_traces) — no-silent-except, 헬퍼 fail-open 회로 가시화
```

**엔진 계약**: 각 스테이지는 typed 입출력 + trace 레코드. retrieve 스테이지(3a/3b)만
교체 가능한 인터페이스 — CAG vs RAG를 동일 testset으로 A/B하는 구조적 전제이자,
게이트 미통과·Kill criteria 발동 시 롤백이 "설정 변경"이 되게 하는 장치.

---

## 3. 데이터 모델 (Supabase/Postgres 단일 스토어)

```
documents  (id, source_type[rule|skill|report|code], title, category, department,
            version, effective_date, git_path, git_commit, status, meta)
  └ sections (id, document_id, breadcrumb "문서명>제3장>제12조", article_no, order)
      └ chunks (id, section_id, text, context_prefix, embedding vector,
                keywords[], token_count, meta)

article_registry (document_id, article_no, article_title, section_id)   ← §5 검증기의 원장
boost_rules      (match_type, pattern, target_filter, boost, reason, created_by,
                  status[shadow|active], eval_run_id)                    ← ADR-5
                  ※ DB 제약: status='active' ⇒ eval_run_id NOT NULL **이고 해당 run 판정=passed**
pinned_citations (질의 패턴 → 보장 인용, 동일 shadow→active 규율)
query_traces     (질의별 스테이지 기록: intake 판정, 검색 쿼리셋, 후보+점수,
                  verify 결과, provider, 지연, 회로 상태)
faq_cache / synonym_dictionary / critical_keywords / hotline_config      ← v1 이식
```

- **부모-자식(small-to-big)**: 검색은 chunk, LLM 컨텍스트는 부모 section 전체.
- **Contextual Retrieval**: 적재 시 chunk마다 1~2문장 맥락 + keywords + category +
  예상질문을 LLM 1콜로 생성해 저장 (v1 auto_* 9종 흡수). 재적재 시 해시 미변경 chunk 스킵.
- **적재 경로 2개**: admin docx 업로드(사규 — v1의 archive·민감차단 로직 이식, 조 단위
  Section 구조화 + article_registry 동시 기록) / git-diff 증분(skill·report·code).
- **조항 정규화 단일 함수**: "제N조·제N조의M" 파싱은 파서·적재기·§5 검증기·답변 인용
  추출기가 **하나의 공유 함수**를 쓴다 — 서로 다른 정규화는 오차단을, 같은 오류의 공유는
  영구 미검출(common-mode failure)을 낳는다. v1 파서 정규식은 조의N을 부모 조로 흡수하는
  결함이 있으므로 개량 필수. 부칙·별표·삭제조항의 registry 포함/제외 정책을 적재 규칙에 명시.
- **재적재는 원자 단위**: 사규 재적재 훅 = (문서 단위 registry 트랜잭션 replace) +
  (CAG 캐시 rebuild) + (faq_cache 무효화) + (golden testset 영향 플래그)를 **한 단위로**
  실행. 하류 소비자 4곳이 서로 다른 적재 스냅샷을 보는 순간 §5 검증기가 정상 인용을
  차단하거나 stale 답변이 나간다 (버전 스큐 일반화).
- **대화 상태**: 모호성 되묻기·후보선택·grounded 후속질문은 정의상 2턴 이상을 요구한다.
  세션 대화 이력(직전 되묻기와 사용자의 선택 포함)이 intake·route에 전달되는 경로를
  엔진 계약에 포함한다 — query_traces는 감사 로그이지 대화 상태 저장소가 아니다.
- **접근 제어**: source_type별 노출 정책(RLS). code·report가 사규 질문 답변에 인용되는
  사고는 스키마 수준에서 차단. **RLS 정책은 명시적으로 부여** — anon SELECT 정책 누락 시
  에러 없이 빈 배열이 반환되는 함정(v1 RLS 마이그레이션 5개가 이 함정의 흔적).

---

## 4. rule 트랙 상세 — CAG-primary 운영 설계

council 심의가 도출한 운영 조건을 코드 계약으로:

1. **캐시 워밍은 요청 경로 밖에서.** v1은 TTL 리프레시가 사용자 요청 경로의 Lock 안에서
   발생(첫 토큰 지연 직결). v2는 백그라운드 스레드/기동 시 pre-warm + TTL 만료 전 갱신.
2. **Invalidation 자동화.** 수동 토큰 운영 금지. 사규 적재/승인 훅이 캐시 drop+rebuild를
   트리거하고, 배포 시 git SHA를 invalidate 토큰으로 자동 세팅. (stale 사규 답변 사고
   1회 = Kill criteria)
2-1. **FAQ 캐시도 신선도 대상.** intake의 FAQ 히트는 verify 이전에 답변이 나가는 유일한
   경로다 — 재적재 훅이 faq_cache를 무효화(또는 재검증 큐 투입)하고, FAQ 큐레이션 답변도
   등록·갱신 시점에 §5 조항 검증기를 통과시킨다. (Kill criteria "stale 사규 답변 사고"의
   최개연 발생 경로가 CAG 캐시가 아니라 여기다.)
3. **캐시 miss 시 풀가격 전송 금지.** miss·빌드 실패·Claude fallback 발동 시 즉시 RAG
   경로 강등. 강등은 저하 서비스임을 신뢰도 칩에 표시하고, 강등 경로도 golden testset
   회귀 대상에 포함.
4. **Critical 프롬프트의 캐시 호환 재설계.** v1은 SDK 제약(cached_content 사용 시
   system_instruction 병용 불가)으로 critical 변형 프롬프트가 캐시를 우회했다. v2는
   critical 지시를 user turn 측에 배치해 캐시 적용률을 유지하되, 게이트 testset에
   critical 케이스를 필수 포함해 검증한다.
5. **코퍼스 concat 포맷**: 문서 경계 마커 + (doc_id, article_no) 구조화 헤더 — §5 검증과
   문서 간 조항 혼동(misattribution) 방지를 겸한다.

## 5. 조항 검증기 (신규 — CAG 채택의 선행 조건)

council 최대 발견: v1 `citation_verifier`는 조항 번호를 **제거한 뒤** doc_title만
매칭한다. 전체 코퍼스가 컨텍스트인 CAG에서는 이 검증이 거의 항상 통과 →
"실재 문서의 비실재 조항"이 완전 사각지대.

v2 검증기는 결정론이다:

```
답변에서 (문서명, 조항번호) 쌍 추출
  → article_registry 대조
    → 실재: 통과
    → 문서는 있는데 조항 없음: 해당 인용 제거·재합성 또는 신뢰도 강등 + trace 기록
    → 문서 자체 없음: 답변 차단 → RAG 강등 재시도 또는 담당부서 라우팅
```

LLM 판단이 아니라 registry 조회다 — 품질 서열 1위(無인용 무결성)를 프롬프트 준수가 아닌
코드로 보증한다. v1 `answer_guard`(contexts 빈 경우 결정적 거절)와 같은 철학의 확장.

## 6. 게이트 3종 (CAG-primary 활성화 조건 — 각각 독립 판정)

| 게이트 | 기준 | 측정 방법 |
|---|---|---|
| G1. 비용 | (코퍼스토큰/4 × 일질의량 + storage token-hour) ≤ RAG 예상비용 × 3 | 측정 킷(동봉 SQL) → 비용 계산기. **이 숫자 없이 활성화 금지** |
| G2. 검증기 | §5 조항 검증기 구현 + article_registry 커버리지 100% | **분모는 파서 출력이 아닌 독립 산출** — 문서별 무작위 1개 장(章) 인간 표본 감사로 대조 (파서가 분모·분자를 다 만들면 자기참조 검증이라 100%가 공허하게 통과한다) |
| G3. 품질 | 동일 golden testset에서 CAG 인용 정확도 ≥ RAG (non-inferiority) | **답변 수준 인용 스코어러**(§5 추출기+registry 재사용, retrieve 비경유 경로도 채점 가능)로 판정 — v1 eval 하니스는 검색 수준 전용이라 CAG를 채점할 수 없다. testset은 카테고리 층화 최소 50문항 + critical·유사 조항 혼동(제23조↔제32조류)·중간부 문서 케이스 필수 (v1 fixtures 규모로는 non-inferiority 통계 불성립) |

**Kill criteria (활성화 후 관측 시 철회·재심의):** 코퍼스가 캐시 상한 근접 / 비용 3배 초과 /
인용 정확도 열위 전환 / 첫 토큰 지연 UX 허용선 초과 / stale 사규 답변 사고 1회 /
critical 질의가 로그상 지배적 비중.

---

## 7. 스택 확정표 (2026-07 검증 기준)

| 레이어 | 확정 | 기각·보류 (사유) |
|---|---|---|
| 임베딩 | **Gemini embedding API** (768, env 추상화 유지) | Qwen3-Embedding·BGE-M3·KURE 셀프호스트 (무GPU·데이터 반출) — eval A/B 슬롯으로만 |
| Lexical | **pgroonga + TokenMecab** (v1 v3 RPC 이식) | Kiwi BM25 신규 구축 (기존이 상위 호환) |
| 융합 | RRF + 메타데이터 필터(SQL 레벨) | 파이썬 후처리 cap (v1 방식 폐기) |
| 리랭커 | **Gemini Flash-Lite listwise** (v1 이식) + helper_health 회로 가시화 | Qwen3-Reranker 셀프호스트 기각 / Cohere Rerank·API형은 A/B 후보 |
| 생성 | **Gemini primary / Claude fallback** (v1 이중화 유지) + 난이도 라우팅(경질의→저비용 모델) | 국산 sovereign 모델: 법령 도메인 특화 필요 판명 시 재검토 |
| 저장 | Supabase pgvector(HNSW) + pgroonga, RLS 명시 정책 | |
| 쿼리 이해 | 원 쿼리 불가침 + 병렬 multi-query(확장은 dense만) + synonym_dictionary | rewriter류 원 쿼리 대체 (v1에서 -98 실증 폐기) |
| 에스컬레이션 | 저신뢰 답변 → agentic search 티어 (도구 반복 호출, 지연 고지 후) | 전 질의 agentic (지연·비용) |

---

## 8. 빌드 순서 (각 Phase 종료 조건 = eval 스코어 + trace 완결성)

- **Phase 0 — 기반+측정 (타임박스 2주)**: 스키마(§3 전체, article_registry 포함) ·
  **검색 수준 eval**(v1 하니스 이식) · query_traces · **측정 킷 실행 → G1 숫자 확보** ·
  RLS 정책 검증 스크립트. 무가시 구간이므로 2주 초과 시 "지금 필요한 최소"로 강제 축소.
- **Phase 1 — RAG 코어**: rule+report 어댑터 → contextual 적재(registry 동시 기록) →
  hybrid 검색 → **리랭커 이식(v1 Flash-Lite — §2 정본 파이프라인과 G3 비교 기준을
  일치시키기 위해 여기서)** → 섹션 계약 합성 → §5 검증기 → **답변 수준 인용 스코어러
  (G3의 계측기 — 이것 완성 후에만 베이스라인 확정)** → **critical 게이트+pii_filter+핫라인
  이식(v1 소형 모듈 — 어떤 형태의 사용자 노출도 이 이전에 금지)** → 최소 UI.
  **eval 베이스라인 확정 (이것이 G3의 비교 기준).**
- **Phase 2 — CAG 트랙**: **첫 작업 = Streamlit 단일 프로세스에서 백그라운드 캐시 워밍
  스레드 동작 검증 스파이크(반나절 — 실패 시 기동 시 warm + 강등 우선으로 §4-1 대체)** →
  캐시 매니저 v2(§4) → G1·G2·G3 판정 → 통과 시 rule 트랙 기본값 전환(미통과 시 RAG
  유지로 종결 — 이것도 유효한 결말이다).
- **Phase 3 — 품질 레이어**: intake 풀구성(모호성 3종 통합·FAQ·OOS) · **대안 리랭커
  (Cohere 등) A/B** · boost_rules admin(shadow→active) · agentic 에스컬레이션.
- **Phase 4 — 확장·자동화**: code/skill 어댑터 · git-diff 증분 적재 CI · auto testset
  연결 · 피드백 루프(👎 → testset 후보) · Kill criteria 모니터 대시보드.

**v1 병행·컷오버**: v1은 Phase 2 종료까지 병행 운영한다. 컷오버 조건 = 동일 golden
testset non-inferiority + 관측 기간 2주 무사고. (second-system 좌초 방지 — v2가 늦어져도
서비스 공백이 없고, 최악의 결말은 "더 깨끗한 v1"이다.)

**eval 운영 2단화**: 검색 수준 eval은 상시·저비용(모든 변경에), 인용 수준 eval은 병합 전·
야간 배치로 — ADR-6의 게이트가 솔로 빌더의 반복 루프를 질식시키지 않게 한다.

---

## 9. v1 이식 판정 최종표 (요약)

✅ **이식**: hybrid_search_v3(pgroonga) · 섹션 계약·prompts · confidence 멀티시그널 ·
FAQ cache · OOS router · critical mode+hotline · synonym_dictionary · pii_filter ·
audit logger · answer_guard · ambiguity/disambiguation/multi_facet(→모호성 스테이지 통합) ·
nexus_reranker(Flash-Lite listwise) · helper_health · docx_parser/ingest(개량) ·
eval 하니스(→Phase 0 승격) · CAG 매니저(→§4로 재설계 승격) · 디자인 시스템(Warm Editorial)

🔁 **재설계 흡수**: auto_* 9종 → contextual 적재 1콜 / golden_citations·EMERGENCY_KEYWORDS·
force-include → boost_rules·pinned_citations 테이블 / citation_verifier → §5 조항 검증기

❌ **폐기**: query_rewriter(원 쿼리 대체) · chatbot.py 모놀리스 · 파이썬 후처리 도메인 cap ·
수동 invalidate 토큰 운영 · 요청 경로 내 캐시 리프레시

---

## 한 줄 요약

> 목적(정확한 조항 근거 + 사람 연결)이 서열을 정하고, 서열이 아키텍처를 정했다:
> **결정론 조항 검증기를 깔고, 사규는 CAG-primary(게이트 조건부)·성장 코퍼스는 RAG,
> 모든 경로 위에 critical 게이트, 모든 변경 앞에 eval.**
