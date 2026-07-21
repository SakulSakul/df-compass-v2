-- ============================================================
-- ADR-8 완화 — nexus_chunks additive 컬럼 + contextual v4 RPC
--
-- [사용자 액션] **기존 v1 프로젝트** SQL Editor 에서 이 파일 전문 1회 실행.
-- (ADR-8 완화 2026-07-21: 신규 테이블·신규 프로젝트는 여전히 금지,
--  nexus_chunks 에 대한 additive 컬럼만 허용)
--
-- v1 무영향 근거 (전수 grep, docs/v1-schema-reflection.md 에 증거 기록):
--   - v1 의 nexus_chunks SELECT 21곳 전부 명시 컬럼 — select("*") 0건.
--   - 쓰기는 update(dict)/insert(dict) 명명 컬럼만 — 신규 컬럼 미인지.
--   - v3 RPC 는 c.embedding 만 참조 — ctx_embedding 미참조.
--   → nullable additive 컬럼은 v1 코드 경로에 관측 불가(무간섭 공존).
-- ============================================================

BEGIN;

-- [1] additive 컬럼 2개 (nullable — 기존 행 영향 없음)
ALTER TABLE nexus_chunks
  ADD COLUMN IF NOT EXISTS ctx_prefix    TEXT,
  ADD COLUMN IF NOT EXISTS ctx_embedding VECTOR(768);

-- [2] HNSW 인덱스 (ctx_embedding — v1 embedding 인덱스와 별개)
CREATE INDEX IF NOT EXISTS idx_nexus_chunks_ctx_embedding
  ON nexus_chunks USING hnsw (ctx_embedding vector_cosine_ops);

-- [3] v2 전용 검색 RPC — v3 전문 복제, vector 경로만 ctx_embedding 사용.
--     시그니처는 v3 와 동일 → v2 래퍼(V1RpcRetriever)가 rpc_name 만 바꿔
--     A/B 한다. keyword(pgroonga)·RRF·필터는 v3 와 동일.
create or replace function nexus_hybrid_search_v4_ctx(
  query_embedding vector(768),
  query_text      text,
  match_count     int default 5,
  rrf_k           int default 60,
  pool_size       int default 30
)
returns table (
  id          uuid,
  document_id uuid,
  text        text,
  article_no  text,
  categories  nexus_category[],
  doc_title   text,
  doc_kind    nexus_doc_kind,
  rrf_score   double precision
)
language sql stable as $$
  with vector_hits as (
    select
      c.id,
      row_number() over (order by c.ctx_embedding <=> query_embedding) as rnk
    from nexus_chunks c
    join nexus_documents d on d.id = c.document_id
    where d.status = 'active'
      and d.superseded_by is null
      and c.ctx_embedding is not null          -- 백필 전 행은 vector 경로 제외
    order by c.ctx_embedding <=> query_embedding
    limit pool_size
  ),
  keyword_hits as (
    select
      c.id,
      row_number() over (
        order by pgroonga_score(c.tableoid, c.ctid) desc
      ) as rnk
    from nexus_chunks c
    join nexus_documents d on d.id = c.document_id
    where d.status = 'active'
      and d.superseded_by is null
      and nullif(trim(query_text), '') is not null
      and c.text &@~ query_text
    order by pgroonga_score(c.tableoid, c.ctid) desc
    limit pool_size
  ),
  fused as (
    select
      coalesce(v.id, k.id) as id,
      (
        coalesce(1.0 / (rrf_k + v.rnk), 0)
        + coalesce(1.0 / (rrf_k + k.rnk), 0)
      )::double precision as rrf_score
    from vector_hits v
    full outer join keyword_hits k on k.id = v.id
  )
  select
    c.id,
    c.document_id,
    c.text,
    c.article_no,
    c.categories,
    d.title       as doc_title,
    d.doc_kind,
    f.rrf_score
  from fused f
  join nexus_chunks c    on c.id = f.id
  join nexus_documents d on d.id = c.document_id
  order by f.rrf_score desc
  limit match_count;
$$;

COMMIT;

NOTIFY pgrst, 'reload schema';
