# v1 스키마 리플렉션 (ADR-8 — v2 의 SELECT 계약 원본)

> v2 는 v1 Supabase(nexus_*)를 **SELECT 전용**으로 사용한다.
> 이 문서는 v2 코드가 의존해도 되는 물리 컬럼·RPC 의 단일 기준이다.
> 갱신 절차: [사용자 액션] tools/schema_reflect.sql 을 v1 SQL Editor 에서
> 실행 → 결과를 이 문서에 붙여넣는다. **레포 SQL 파일로 추정하지 말 것**
> (마이그레이션 누적 결과 ≠ 개별 파일; RPC 반환 키 ≠ 물리 컬럼).

## 상태

- 최종 리플렉션: **미실행** — [사용자 액션] 대기.
- 리플렉션 전까지 v2 코드는 아래 "잠정 계약(코드 근거)"의 컬럼만 사용한다 —
  전부 v1 운영 코드가 실제로 SELECT/RPC 로 쓰고 있는 검증된 표면이다.

## 잠정 계약 (v1 운영 코드 근거 — 리플렉션으로 확정 예정)

### nexus_chunks (파생 원장·검색 소비)
| 컬럼 | 근거 |
|---|---|
| id, document_id, text | v1 retriever/force-include 경로 다수 |
| article_no | ⚠️ **v2 사용 금지** — v1 파서의 조의N 붕괴 가능성. 원장은 text 재추출만 (ADR-8) |

### nexus_documents
| 컬럼 | 근거 |
|---|---|
| id, title, doc_kind, status, superseded_by | v1 retriever·RPC WHERE 절 |

### RPC: nexus_hybrid_search_v3_pgroonga (v2 검색 진입점)
```
args: query_embedding vector(768), query_text text,
      match_count int=5, rrf_k int=60, pool_size int=30
returns: id uuid, document_id uuid, text text, article_no text,
         categories nexus_category[], doc_title text,
         doc_kind nexus_doc_kind, rrf_score double precision
```
근거: v1 db/migrations/20260513_nexus_hybrid_search_v3_pgroonga.sql +
core/retriever.py 호출부(payload 미러). 리플렉션 [R2] 로 확정 예정.

## additive 컬럼 v1 무영향 증거 (ADR-8a, 2026-07-21 전수 grep)

`ctx_prefix TEXT` / `ctx_embedding VECTOR(768)` (nullable) 추가가 v1 동작에
영향 없음을 v1 레포 전수 grep 으로 확인:

1. **SELECT**: `table("nexus_chunks")` 접근 21곳(core/retriever 10 · core/auto 7 ·
   core/nexus_cag_manager 1 · pages/admin 3) 전부 **명시 컬럼** select.
   `select("*")`·무인자 select **0건** → 신규 컬럼이 응답에 실리지 않는다.
2. **쓰기**: `update(dict)` 2곳(auto/chunk_meta_filler:133, auto/auto_fixer:303)·
   `insert(dict rows)` 1곳(parser/ingest.py:145) — 전부 명명 컬럼 dict.
   신규 nullable 컬럼은 미지정 시 NULL → 기존 경로 불변.
3. **RPC**: v3(nexus_hybrid_search_v3_pgroonga)는 `c.embedding`·`c.text` 등
   기존 컬럼만 참조 — `ctx_embedding` 미참조.
→ v1=embedding, v2=ctx_embedding 을 읽으므로 같은 테이블에서 무간섭 공존.

## 리플렉션 결과 (붙여넣기 영역)

### [R1] nexus_* 컬럼 덤프
_(미실행)_

### [R2] RPC 시그니처 덤프 (2026-07-22 사용자 회신 — 확정)

| function_name | args | returns |
|---|---|---|
| nexus_chunks_tsv_trigger | | trigger |
| nexus_diagnose_incident_node_matching | p_nodes text[] | TABLE(doc_id uuid, doc_title text, doc_status text, doc_incident_nodes jsonb, matched_nodes text[], total_chunks integer) |
| nexus_diagnose_role | | TABLE(curr_user text, curr_role text, sess_user text, curr_schema text, curr_database text) |
| nexus_force_include_chunks_by_incident_nodes | p_nodes text[] | TABLE(id uuid, document_id uuid, chunk_idx integer, article_no text, text text, doc_title text, doc_incident_nodes jsonb, matched_node_count integer) |
| nexus_hybrid_search | query_text text, query_embed vector, filter_categories nexus_category[] DEFAULT NULL, filter_doc_kinds nexus_doc_kind[] DEFAULT NULL, top_k integer DEFAULT 3, fanout integer DEFAULT 30, rrf_k integer DEFAULT 60, fallback_to_common boolean DEFAULT true, as_of_date date DEFAULT CURRENT_DATE | TABLE(chunk_id uuid, document_id uuid, doc_title text, doc_kind nexus_doc_kind, article_no text, case_no text, text text, score double precision, owning_department text, categories nexus_category[]) |
| nexus_hybrid_search_v2 | query_embedding vector, query_text text, match_count integer DEFAULT 5, rrf_k integer DEFAULT 60, pool_size integer DEFAULT 30 | TABLE(id uuid, document_id uuid, text text, article_no text, categories nexus_category[], doc_title text, doc_kind nexus_doc_kind, rrf_score double precision) |
| nexus_hybrid_search_v3_pgroonga | (v2 와 동일 args) | (v2 와 동일 returns) |
| nexus_hybrid_search_v4_ctx | (v2 와 동일 args) | (v2 와 동일 returns) |

**대조 판정 (v2 잠정 계약 대비):**
- `v3_pgroonga` — 잠정 계약과 **완전 일치** → V1RpcRetriever payload 확정.
- `v4_ctx` — **실재 확인** (additive SQL 의 DB 반영 독립 증거), v3 와 시그니처
  동일 → 래퍼 rpc_name 교체 방식 유효 확정.
- v2 는 v1/v2(구) RPC·diagnose·force_include RPC 를 호출하지 않는다 —
  목록은 참고용 전수 기록.
