-- ============================================================
-- DF COMPASS v2 · 게이트 1 측정 킷
-- 실행 대상: 현행 v1 Supabase (nexus_documents / nexus_chunks / query_logs)
-- Supabase SQL Editor에 섹션별로 붙여넣어 실행.
-- 결과 4개 숫자를 cost_calculator.py 에 입력하면 G1 판정이 나온다.
-- ============================================================

-- ── [M1] 사규 코퍼스 토큰 수 (CAG 캐시 대상 크기) ─────────────
-- token_count 컬럼이 채워져 있으면 그 합, 비어 있으면 한국어 근사
-- (chars / 2.0 ~ 2.5 → 보수적으로 /2.0 상한, /2.5 하한 병기)
select
  d.doc_kind,
  count(distinct d.id)                                   as docs,
  count(c.id)                                            as chunks,
  sum(coalesce(c.token_count, 0))                        as tokens_measured,
  round(sum(char_length(c.text)) / 2.5)                  as tokens_est_low,
  round(sum(char_length(c.text)) / 2.0)                  as tokens_est_high
from nexus_documents d
join nexus_chunks c on c.document_id = d.id
where d.status = 'active'
group by rollup (d.doc_kind)
order by d.doc_kind nulls last;
-- → 맨 아래 rollup 행의 tokens_est_high 를 CORPUS_TOKENS 로 사용 (보수 추정)

-- ── [M2] 문서별 상위 크기 (캐시 상한 접근 시 분리 후보 파악) ──
select d.title, d.doc_kind,
       count(c.id) as chunks,
       round(sum(char_length(c.text)) / 2.0) as tokens_est
from nexus_documents d
join nexus_chunks c on c.document_id = d.id
where d.status = 'active'
group by d.id, d.title, d.doc_kind
order by tokens_est desc
limit 20;

-- ── [M3] 일일 질의량 (최근 90일, 평균·피크) ──────────────────
select
  count(*)                                          as total_90d,
  round(count(*) / 90.0, 1)                         as avg_per_day,
  max(daily.cnt)                                    as peak_day,
  percentile_cont(0.95) within group (order by daily.cnt) as p95_day
from query_logs q,
lateral (
  select count(*) as cnt
  from query_logs q2
  where q2.ts::date = q.ts::date
) daily
where q.ts >= now() - interval '90 days';
-- (위 lateral이 무겁게 돌면 아래 단순판 사용)
-- select ts::date as day, count(*) from query_logs
--  where ts >= now() - interval '90 days'
--  group by 1 order by 1;
-- → avg_per_day 를 DAILY_QUERIES 로 사용

-- ── [M4] critical 질의 비중 (캐시 우회/특수 경로 트래픽 규모) ──
select
  count(*) filter (where is_critical)                    as critical_cnt,
  count(*)                                               as total_cnt,
  round(100.0 * count(*) filter (where is_critical) / nullif(count(*),0), 1)
                                                         as critical_pct
from query_logs
where ts >= now() - interval '90 days';
-- → critical_pct 가 지배적(예: 30%+)이면 CAG-primary 실효 적용률 재평가 (Kill criteria)

-- ── [M5] RAG 질의당 평균 컨텍스트 토큰 (비교 기준선) ──────────
-- hit_chunk_ids 기반: 실제로 top-k에 실려 나간 청크들의 토큰 합의 평균
select
  round(avg(ctx.tokens_est))  as avg_rag_context_tokens,
  round(percentile_cont(0.95) within group (order by ctx.tokens_est)) as p95
from query_logs q,
lateral (
  select sum(round(char_length(c.text) / 2.0)) as tokens_est
  from nexus_chunks c
  where c.id = any(q.hit_chunk_ids)
) ctx
where q.ts >= now() - interval '90 days'
  and q.hit_chunk_ids is not null;
-- → avg_rag_context_tokens 를 RAG_CTX_TOKENS 로 사용
