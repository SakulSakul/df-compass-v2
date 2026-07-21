-- ============================================================
-- DF COMPASS v2 · 정본 스키마 (DESIGN.md §3 전체)
-- Phase 0 초기 상태 = db/migrations/0001_phase0_init.sql 적용 결과.
--
-- ⚠️ 실행 전제: 반드시 **v2 전용 신규 Supabase 프로젝트**에서 실행.
--    v1 운영 프로젝트 실행 금지 — v1 의 01_schema.sql 이 무접두어
--    critical_keywords / hotline_config 를 이미 생성했고(운영 중
--    critical_mode.py 가 읽는 실테이블), 같은 프로젝트에서 실행하면
--    CREATE IF NOT EXISTS 는 스킵되지만 ENABLE RLS 가 v1 운영 테이블에
--    적용되어 critical 감지가 silent fail 한다. 아래 v1 감지 가드가
--    이 경우 실행을 즉시 중단시킨다 (안전벨트).
--
-- [사용자 액션] 신규 v2 프로젝트의 SQL Editor 에 이 파일 전문을 붙여넣어 1회 실행.
--   (이후 스키마 변경은 migrations/ 에 번호 파일로 추가되고,
--    이 스냅샷은 각 마이그레이션 반영 시 함께 갱신된다)
--
-- 설계 근거:
-- - 부모-자식(small-to-big): 검색=chunks, LLM 컨텍스트=부모 sections.
-- - article_registry = §5 결정론 조항 검증기의 원장.
-- - boost_rules/pinned_citations: shadow→active + eval 게이트(ADR-5) —
--   DB 제약: active ⇒ eval_run_id NOT NULL 이고 해당 run 판정=passed (트리거).
-- - RLS 는 명시적 부여(§3): anon 은 rule 트랙 active 문서만 읽는다.
--   code·report 는 스키마 수준 차단. 정책 없는 테이블은 "의도된 비공개"를
--   주석으로 명시 (anon SELECT 가 에러 없이 빈 배열을 주는 함정 대응은
--   canary 행 + tools/rls_verify.py 로 결정론 검증).
-- - G1 미통과(2026-07-21) → rule 트랙 RAG 확정. CAG 전용 객체는 없다.
-- ============================================================

BEGIN;

-- ── v1 감지 가드 (안전벨트) — v1 프로젝트에서 실행 시 즉시 중단 ──
DO $$
BEGIN
  IF to_regclass('public.nexus_documents') IS NOT NULL THEN
    RAISE EXCEPTION
      '이 프로젝트는 v1(DF COMPASS) 운영 프로젝트입니다. v2 스키마는 반드시 신규 전용 프로젝트에서 실행하세요 — 여기서 실행하면 v1 운영 테이블(critical_keywords/hotline_config)에 RLS 가 걸려 critical 감지가 중단됩니다.';
  END IF;
END $$;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgroonga;

-- ── 코퍼스 3계층 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type    TEXT NOT NULL CHECK (source_type IN ('rule','skill','report','code')),
  title          TEXT NOT NULL,
  category       TEXT,
  department     TEXT,
  version        TEXT,
  effective_date DATE,
  git_path       TEXT,             -- skill/report/code 트랙 (git-diff 증분 적재)
  git_commit     TEXT,
  status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived','draft')),
  meta           JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sections (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  breadcrumb   TEXT NOT NULL,      -- "문서명>제3장>제12조"
  article_no   TEXT,               -- articles.canonical 정규형 ("제3조의2" 등)
  ord          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sections_doc ON sections(document_id, ord);

CREATE TABLE IF NOT EXISTS chunks (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  section_id     UUID NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  text           TEXT NOT NULL,
  context_prefix TEXT NOT NULL DEFAULT '',   -- Contextual Retrieval 1~2문장 (적재 1콜)
  embedding      VECTOR(768),                -- Gemini embedding — Phase 1 적재 시 기입
  keywords       TEXT[] NOT NULL DEFAULT '{}',
  token_count    INTEGER,
  meta           JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks
  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_pgroonga ON chunks
  USING pgroonga (text) WITH (tokenizer = 'TokenMecab');

-- ── §5 검증기 원장 ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS article_registry (
  document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  article_no    TEXT NOT NULL,     -- articles.canonical 정규형 단일 기준
  article_title TEXT,
  section_id    UUID REFERENCES sections(id) ON DELETE SET NULL,
  PRIMARY KEY (document_id, article_no)
);

-- ── eval 게이트 (ADR-5/6 의 전제) ───────────────────────────
CREATE TABLE IF NOT EXISTS eval_runs (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT NOT NULL,
  verdict    TEXT NOT NULL DEFAULT 'running' CHECK (verdict IN ('running','passed','failed')),
  metrics    JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS boost_rules (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  match_type   TEXT NOT NULL CHECK (match_type IN ('substring','regex','category')),
  pattern      TEXT NOT NULL,
  target_filter JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {source_type, document_id, ...}
  boost        DOUBLE PRECISION NOT NULL,
  reason       TEXT NOT NULL,
  created_by   TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'shadow' CHECK (status IN ('shadow','active')),
  eval_run_id  UUID REFERENCES eval_runs(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- active ⇒ eval_run_id 필수 (판정=passed 는 아래 트리거가 보증)
  CONSTRAINT boost_active_needs_eval CHECK (status <> 'active' OR eval_run_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS pinned_citations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  match_type   TEXT NOT NULL CHECK (match_type IN ('substring','regex')),
  pattern      TEXT NOT NULL,             -- 질의 패턴
  document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  article_no   TEXT,                      -- NULL = 문서 단위 보장
  reason       TEXT NOT NULL,
  created_by   TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'shadow' CHECK (status IN ('shadow','active')),
  eval_run_id  UUID REFERENCES eval_runs(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pin_active_needs_eval CHECK (status <> 'active' OR eval_run_id IS NOT NULL)
);

-- active 전환은 판정=passed 인 eval run 만 허용 (CHECK 는 타 테이블 참조 불가 → 트리거)
CREATE OR REPLACE FUNCTION enforce_eval_gate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'active' AND NOT EXISTS (
    SELECT 1 FROM eval_runs WHERE id = NEW.eval_run_id AND verdict = 'passed'
  ) THEN
    RAISE EXCEPTION 'shadow→active 는 판정=passed 인 eval_run_id 필수 (ADR-5)';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_boost_eval_gate ON boost_rules;
CREATE TRIGGER trg_boost_eval_gate BEFORE INSERT OR UPDATE ON boost_rules
  FOR EACH ROW EXECUTE FUNCTION enforce_eval_gate();
DROP TRIGGER IF EXISTS trg_pin_eval_gate ON pinned_citations;
CREATE TRIGGER trg_pin_eval_gate BEFORE INSERT OR UPDATE ON pinned_citations
  FOR EACH ROW EXECUTE FUNCTION enforce_eval_gate();

-- ── trace (감사 로그 — 대화 상태 저장소 아님, §3) ───────────
CREATE TABLE IF NOT EXISTS query_traces (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id    TEXT NOT NULL,
  stage       TEXT NOT NULL CHECK (stage IN ('intake','route','retrieve','verify','render')),
  started_at  TIMESTAMPTZ NOT NULL,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  ok          BOOLEAN NOT NULL,
  error       TEXT,                        -- 실패는 반드시 기록 (silent fail 금지)
  circuit     JSONB NOT NULL DEFAULT '{}'::jsonb,   -- helper fail-open 회로 상태
  payload     JSONB NOT NULL DEFAULT '{}'::jsonb,   -- 스테이지 입출력 요약 (PII 마스킹 후)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_traces_query ON query_traces(query_id, started_at);

-- ── v1 이식 4종 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS faq_cache (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_normalized TEXT NOT NULL UNIQUE,
  query_display    TEXT NOT NULL,
  answer_text      TEXT NOT NULL DEFAULT '',
  category         TEXT,
  is_critical      BOOLEAN NOT NULL DEFAULT false,  -- true 면 서빙 금지 (핫라인 우회 차단)
  source           TEXT NOT NULL DEFAULT 'manual',
  approved         BOOLEAN NOT NULL DEFAULT false,
  approved_by      TEXT,
  approved_at      TIMESTAMPTZ,
  stale            BOOLEAN NOT NULL DEFAULT false,  -- 재적재 훅이 true 로 → 재검증 큐 (§4-2-1)
  hit_count        INTEGER NOT NULL DEFAULT 0,
  last_hit_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS synonym_dictionary (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  primary_term  TEXT NOT NULL,
  synonym_term  TEXT NOT NULL,
  evidence_text TEXT,
  extraction_method TEXT NOT NULL DEFAULT 'manual',
  confidence    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  approved      BOOLEAN NOT NULL DEFAULT false,
  rejected      BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (primary_term, synonym_term)
);

CREATE TABLE IF NOT EXISTS critical_keywords (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  term       TEXT NOT NULL UNIQUE,
  kind       TEXT NOT NULL,                -- safety|harassment|privacy|crime ... (핫라인 매핑 키)
  active     BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hotline_config (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  description TEXT,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- v1 선례: anon 에는 key/value 만 노출 (description/updated_at 누설 차단)
CREATE OR REPLACE VIEW hotline_config_public AS
  SELECT key, value FROM hotline_config;

-- ── RLS — 명시적 부여 (§3) ──────────────────────────────────
ALTER TABLE documents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE sections         ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks           ENABLE ROW LEVEL SECURITY;
ALTER TABLE article_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_runs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE boost_rules      ENABLE ROW LEVEL SECURITY;
ALTER TABLE pinned_citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_traces     ENABLE ROW LEVEL SECURITY;
ALTER TABLE faq_cache        ENABLE ROW LEVEL SECURITY;
ALTER TABLE synonym_dictionary ENABLE ROW LEVEL SECURITY;
ALTER TABLE critical_keywords  ENABLE ROW LEVEL SECURITY;
ALTER TABLE hotline_config     ENABLE ROW LEVEL SECURITY;

-- anon 읽기 = rule 트랙 active 문서 계층만. code·report 는 스키마 수준 차단.
DROP POLICY IF EXISTS anon_read_rule_documents ON documents;
CREATE POLICY anon_read_rule_documents ON documents FOR SELECT TO anon
  USING (source_type = 'rule' AND status = 'active');

DROP POLICY IF EXISTS anon_read_rule_sections ON sections;
CREATE POLICY anon_read_rule_sections ON sections FOR SELECT TO anon
  USING (EXISTS (SELECT 1 FROM documents d
                 WHERE d.id = document_id
                   AND d.source_type = 'rule' AND d.status = 'active'));

DROP POLICY IF EXISTS anon_read_rule_chunks ON chunks;
CREATE POLICY anon_read_rule_chunks ON chunks FOR SELECT TO anon
  USING (EXISTS (SELECT 1 FROM sections s JOIN documents d ON d.id = s.document_id
                 WHERE s.id = section_id
                   AND d.source_type = 'rule' AND d.status = 'active'));

DROP POLICY IF EXISTS anon_read_rule_registry ON article_registry;
CREATE POLICY anon_read_rule_registry ON article_registry FOR SELECT TO anon
  USING (EXISTS (SELECT 1 FROM documents d
                 WHERE d.id = document_id
                   AND d.source_type = 'rule' AND d.status = 'active'));

-- 의도된 비공개 (anon 정책 없음 — 서비스 role 전용):
--   eval_runs · boost_rules · pinned_citations · query_traces
--   faq_cache · synonym_dictionary · critical_keywords · hotline_config(view 로만)
-- "정책 부재 = 빈 배열" 함정은 아래 canary + tools/rls_verify.py 가 결정론 검증.

-- ── RLS canary seed (검증 스크립트 전용 — 삭제 금지) ────────
INSERT INTO hotline_config (key, value, description)
VALUES ('rls_canary', 'ok', 'tools/rls_verify.py 전용 canary — 삭제 금지')
ON CONFLICT (key) DO NOTHING;

DO $$
DECLARE
  rule_doc UUID; report_doc UUID; rule_sec UUID; report_sec UUID;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM documents WHERE title = '__rls_canary_rule__') THEN
    INSERT INTO documents (source_type, title, status)
    VALUES ('rule', '__rls_canary_rule__', 'active') RETURNING id INTO rule_doc;
    INSERT INTO sections (document_id, breadcrumb, article_no, ord)
    VALUES (rule_doc, '__rls_canary_rule__>제1조', '제1조', 0) RETURNING id INTO rule_sec;
    INSERT INTO chunks (section_id, text) VALUES (rule_sec, 'rls canary rule chunk');
    INSERT INTO article_registry (document_id, article_no, article_title, section_id)
    VALUES (rule_doc, '제1조', 'canary', rule_sec);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM documents WHERE title = '__rls_canary_report__') THEN
    INSERT INTO documents (source_type, title, status)
    VALUES ('report', '__rls_canary_report__', 'active') RETURNING id INTO report_doc;
    INSERT INTO sections (document_id, breadcrumb, ord)
    VALUES (report_doc, '__rls_canary_report__>본문', 0) RETURNING id INTO report_sec;
    INSERT INTO chunks (section_id, text) VALUES (report_sec, 'rls canary report chunk');
  END IF;
END $$;

COMMIT;

NOTIFY pgrst, 'reload schema';
