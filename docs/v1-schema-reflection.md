# v1 스키마 리플렉션 (ADR-8 — v2 의 SELECT 계약 원본)

> v2 는 v1 Supabase(nexus_*)를 **SELECT 전용**으로 사용한다.
> 이 문서는 v2 코드가 의존해도 되는 물리 컬럼·RPC 의 단일 기준이다.
> 갱신 절차: [사용자 액션] tools/schema_reflect.sql 을 v1 SQL Editor 에서
> 실행 → 결과를 이 문서에 붙여넣는다. **레포 SQL 파일로 추정하지 말 것**
> (마이그레이션 누적 결과 ≠ 개별 파일; RPC 반환 키 ≠ 물리 컬럼).

## 상태

- 최종 리플렉션: **확정** — R1(컬럼)·R2(RPC) 모두 2026-07-22 사용자 실행·회신 완료.
- v2 가 사용하는 전 컬럼이 물리 실재로 확정됨. "잠정 계약" 절은 확정 근거로 유지.
- ⚠️ 리플렉션이 드러낸 v1 측 관찰(수정 금지 — 보고만): `chunk_incident_nodes` 는
  **물리 컬럼이 아님**(R1 전수에 부재)에도 v1 core/retriever.py:1595 의
  `.select()` 에 포함되어 있음 — 해당 경로 42703 소지 (v1 17시간 사고와 동일 클래스).

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

### [R1] nexus_* 컬럼 덤프 (2026-07-22 사용자 회신 — 확정)

10개 테이블 전수. **핵심 확정 사항:**
- `nexus_chunks` (15컬럼): id·document_id·chunk_idx·article_no·case_no·
  categories·text·text_tsv·embedding·token_count·created_at·
  embed_model_version·auto_keywords·**ctx_prefix·ctx_embedding** —
  additive 2컬럼 물리 실재 확인. **`chunk_incident_nodes` 부재**
  (RPC 계산 키 ≠ 물리 컬럼 — v1 17시간 사고 재확인).
- `nexus_documents` (16컬럼): id·title·doc_kind·source_filename·version·
  effective_date·superseded_by·status·uploaded_by·uploaded_at·meta·
  owning_department·source_storage_path·auto_keywords·auto_summary·
  auto_query_examples. (`department` 아님 — `owning_department`.)
- 기타 테이블: nexus_audit_logs(18) · nexus_classification_cache(7) ·
  nexus_critical_hotlines(6) · nexus_faq_cache(18) · nexus_golden_cache(8) ·
  nexus_synonym_dictionary(15) · nexus_validation_queries(8) ·
  nexus_validation_results(14) · nexus_validation_runs(10).
- token_count nullable (G1 측정 시 미기입 상태였던 것과 정합).

<details><summary>원본 덤프 전문 (140행)</summary>

| table_name | pos | column_name | data_type | nullable |
|---|---|---|---|---|
| nexus_audit_logs | 1 | id | uuid | NO |
| nexus_audit_logs | 2 | created_at | timestamptz | NO |
| nexus_audit_logs | 3 | source | text | NO |
| nexus_audit_logs | 4 | query | text | NO |
| nexus_audit_logs | 5 | rewritten_query | text | YES |
| nexus_audit_logs | 6 | incident_nodes | jsonb | YES |
| nexus_audit_logs | 7 | retrieved_chunk_ids | jsonb | YES |
| nexus_audit_logs | 8 | retrieved_chunk_count | integer | YES |
| nexus_audit_logs | 9 | gemini_model_id | text | YES |
| nexus_audit_logs | 10 | gemini_answer | text | YES |
| nexus_audit_logs | 11 | gemini_latency_ms | integer | YES |
| nexus_audit_logs | 12 | claude_model_id | text | YES |
| nexus_audit_logs | 13 | claude_verdict | text | YES |
| nexus_audit_logs | 14 | claude_score | numeric | YES |
| nexus_audit_logs | 15 | claude_report | jsonb | YES |
| nexus_audit_logs | 16 | claude_latency_ms | integer | YES |
| nexus_audit_logs | 17 | total_latency_ms | integer | YES |
| nexus_audit_logs | 18 | notes | text | YES |
| nexus_chunks | 1 | id | uuid | NO |
| nexus_chunks | 2 | document_id | uuid | NO |
| nexus_chunks | 3 | chunk_idx | integer | NO |
| nexus_chunks | 4 | article_no | text | YES |
| nexus_chunks | 5 | case_no | text | YES |
| nexus_chunks | 6 | categories | ARRAY | NO |
| nexus_chunks | 7 | text | text | NO |
| nexus_chunks | 8 | text_tsv | tsvector | YES |
| nexus_chunks | 9 | embedding | USER-DEFINED(vector) | YES |
| nexus_chunks | 10 | token_count | integer | YES |
| nexus_chunks | 11 | created_at | timestamptz | NO |
| nexus_chunks | 12 | embed_model_version | text | YES |
| nexus_chunks | 13 | auto_keywords | jsonb | YES |
| nexus_chunks | 14 | ctx_prefix | text | YES |
| nexus_chunks | 15 | ctx_embedding | USER-DEFINED(vector) | YES |
| nexus_classification_cache | 1 | id | uuid | NO |
| nexus_classification_cache | 2 | query_normalized | text | NO |
| nexus_classification_cache | 3 | incident_nodes | jsonb | NO |
| nexus_classification_cache | 4 | model_id | text | NO |
| nexus_classification_cache | 5 | hit_count | integer | YES |
| nexus_classification_cache | 6 | created_at | timestamptz | NO |
| nexus_classification_cache | 7 | last_used_at | timestamptz | NO |
| nexus_critical_hotlines | 1 | kind | text | NO |
| nexus_critical_hotlines | 2 | title | text | NO |
| nexus_critical_hotlines | 3 | message | text | NO |
| nexus_critical_hotlines | 4 | contact | text | NO |
| nexus_critical_hotlines | 5 | updated_at | timestamptz | NO |
| nexus_critical_hotlines | 6 | updated_by | text | YES |
| nexus_documents | 1 | id | uuid | NO |
| nexus_documents | 2 | title | text | NO |
| nexus_documents | 3 | doc_kind | USER-DEFINED | NO |
| nexus_documents | 4 | source_filename | text | YES |
| nexus_documents | 5 | version | text | NO |
| nexus_documents | 6 | effective_date | date | YES |
| nexus_documents | 7 | superseded_by | uuid | YES |
| nexus_documents | 8 | status | USER-DEFINED | NO |
| nexus_documents | 9 | uploaded_by | text | YES |
| nexus_documents | 10 | uploaded_at | timestamptz | NO |
| nexus_documents | 11 | meta | jsonb | NO |
| nexus_documents | 12 | owning_department | text | YES |
| nexus_documents | 13 | source_storage_path | text | YES |
| nexus_documents | 14 | auto_keywords | jsonb | YES |
| nexus_documents | 15 | auto_summary | text | YES |
| nexus_documents | 16 | auto_query_examples | jsonb | YES |
| nexus_faq_cache | 1 | id | uuid | NO |
| nexus_faq_cache | 2 | query_normalized | text | NO |
| nexus_faq_cache | 3 | query_display | text | NO |
| nexus_faq_cache | 4 | answer_text | text | NO |
| nexus_faq_cache | 5 | category | USER-DEFINED | YES |
| nexus_faq_cache | 6 | is_critical | boolean | NO |
| nexus_faq_cache | 7 | incident_nodes | jsonb | YES |
| nexus_faq_cache | 8 | source | text | NO |
| nexus_faq_cache | 9 | approved | boolean | NO |
| nexus_faq_cache | 10 | approved_by | text | YES |
| nexus_faq_cache | 11 | approved_at | timestamptz | YES |
| nexus_faq_cache | 12 | hit_count | integer | YES |
| nexus_faq_cache | 13 | last_hit_at | timestamptz | YES |
| nexus_faq_cache | 14 | created_at | timestamptz | NO |
| nexus_faq_cache | 15 | updated_at | timestamptz | NO |
| nexus_faq_cache | 16 | show_on_home | boolean | NO |
| nexus_faq_cache | 17 | home_label | text | YES |
| nexus_faq_cache | 18 | home_order | integer | NO |
| nexus_golden_cache | 1 | id | uuid | NO |
| nexus_golden_cache | 2 | incident_signature | text | NO |
| nexus_golden_cache | 3 | expected_clauses | jsonb | NO |
| nexus_golden_cache | 4 | required_docs | jsonb | YES |
| nexus_golden_cache | 5 | model_id | text | NO |
| nexus_golden_cache | 6 | hit_count | integer | YES |
| nexus_golden_cache | 7 | created_at | timestamptz | NO |
| nexus_golden_cache | 8 | last_used_at | timestamptz | NO |
| nexus_synonym_dictionary | 1 | id | uuid | NO |
| nexus_synonym_dictionary | 2 | primary_term | text | NO |
| nexus_synonym_dictionary | 3 | synonym_term | text | NO |
| nexus_synonym_dictionary | 4 | source_doc_id | uuid | YES |
| nexus_synonym_dictionary | 5 | source_chunk_id | uuid | YES |
| nexus_synonym_dictionary | 6 | evidence_text | text | YES |
| nexus_synonym_dictionary | 7 | extraction_method | text | NO |
| nexus_synonym_dictionary | 8 | confidence | double precision | YES |
| nexus_synonym_dictionary | 9 | approved | boolean | NO |
| nexus_synonym_dictionary | 10 | approved_by | text | YES |
| nexus_synonym_dictionary | 11 | approved_at | timestamptz | YES |
| nexus_synonym_dictionary | 12 | rejected | boolean | NO |
| nexus_synonym_dictionary | 13 | rejected_at | timestamptz | YES |
| nexus_synonym_dictionary | 14 | created_at | timestamptz | NO |
| nexus_synonym_dictionary | 15 | updated_at | timestamptz | NO |
| nexus_validation_queries | 1 | id | bigint | NO |
| nexus_validation_queries | 2 | query_text | text | NO |
| nexus_validation_queries | 3 | category | text | YES |
| nexus_validation_queries | 4 | expected_button | text | YES |
| nexus_validation_queries | 5 | note | text | YES |
| nexus_validation_queries | 6 | is_active | boolean | YES |
| nexus_validation_queries | 7 | created_at | timestamptz | YES |
| nexus_validation_queries | 8 | updated_at | timestamptz | YES |
| nexus_validation_results | 1 | id | bigint | NO |
| nexus_validation_results | 2 | run_id | bigint | NO |
| nexus_validation_results | 3 | query_idx | integer | NO |
| nexus_validation_results | 4 | query_text | text | NO |
| nexus_validation_results | 5 | answer_text | text | YES |
| nexus_validation_results | 6 | answer_chars | integer | YES |
| nexus_validation_results | 7 | elapsed_seconds | real | YES |
| nexus_validation_results | 8 | is_critical | boolean | YES |
| nexus_validation_results | 9 | confidence | text | YES |
| nexus_validation_results | 10 | matched_doc_count | integer | YES |
| nexus_validation_results | 11 | cited_docs | jsonb | YES |
| nexus_validation_results | 12 | button_type | text | YES |
| nexus_validation_results | 13 | error | text | YES |
| nexus_validation_results | 14 | created_at | timestamptz | NO |
| nexus_validation_runs | 1 | id | bigint | NO |
| nexus_validation_runs | 2 | started_at | timestamptz | NO |
| nexus_validation_runs | 3 | completed_at | timestamptz | YES |
| nexus_validation_runs | 4 | total_queries | integer | NO |
| nexus_validation_runs | 5 | completed_queries | integer | NO |
| nexus_validation_runs | 6 | status | text | NO |
| nexus_validation_runs | 7 | note | text | YES |
| nexus_validation_runs | 8 | created_at | timestamptz | NO |
| nexus_validation_runs | 9 | model_id | text | YES |
| nexus_validation_runs | 10 | provider | text | YES |

</details>

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
