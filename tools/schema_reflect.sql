-- v1 스키마 리플렉션 (ADR-8 — 읽기 전용, DDL 아님)
--
-- [사용자 액션] v1 Supabase SQL Editor 에서 아래 두 쿼리를 실행하고
-- 결과를 회신 → docs/v1-schema-reflection.md 에 기록된다.
-- 목적: v2 코드가 .select() 에 넣는 모든 컬럼을 "실테이블 기준"으로 고정
-- (RPC 반환 키 ≠ 물리 컬럼 — v1 chunk_incident_nodes 17시간 사고의 교훈).

-- [R1] nexus_* 실테이블 · 컬럼 · 타입
SELECT table_name, ordinal_position, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name LIKE 'nexus_%'
ORDER BY table_name, ordinal_position;

-- [R2] v2 가 호출할 RPC 목록 (시그니처 확인용)
SELECT p.proname AS function_name,
       pg_get_function_arguments(p.oid)  AS args,
       pg_get_function_result(p.oid)     AS returns
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND p.proname LIKE 'nexus_%'
ORDER BY p.proname;
