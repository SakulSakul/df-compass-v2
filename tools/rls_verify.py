"""RLS 검증 — anon 키 관점에서 정책이 '실제로' 의도대로인지 결정론 검사.

핵심 함정(DESIGN.md §3): RLS enabled + 정책 누락 테이블에 anon SELECT 를 하면
에러가 아니라 **빈 배열**이 온다. 그래서 "SELECT 성공 = 정책 있음"이 아니다.
본 스크립트는 마이그레이션이 심은 canary 행으로 판별한다:
  - 읽혀야 하는 곳: canary 가 **보이면** 통과, 빈 배열이면 정책 누락(실패).
  - 막혀야 하는 곳: 빈 배열/거부면 통과, 행이 보이면 노출 사고(실패).

사용법 (Supabase anon 키만 필요 — service 키 사용 금지):
    SUPABASE_URL=... SUPABASE_ANON_KEY=... python tools/rls_verify.py

의존성 없음 (urllib 사용). 종료코드: 0=전부 통과, 1=실패 있음, 2=환경 미설정.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
KEY = os.environ.get("SUPABASE_ANON_KEY") or ""


def _get(path: str) -> tuple[int, list | dict | None]:
    req = urllib.request.Request(
        f"{URL}/rest/v1/{path}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        print(f"  ! 네트워크 오류: {type(e).__name__}: {e}", file=sys.stderr)
        return -1, None


def _post(path: str, body: dict) -> int:
    req = urllib.request.Request(
        f"{URL}/rest/v1/{path}",
        data=json.dumps(body).encode(),
        headers={
            "apikey": KEY, "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json", "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1


def main() -> int:
    if not URL or not KEY:
        print("ERROR: SUPABASE_URL / SUPABASE_ANON_KEY 환경변수 필요", file=sys.stderr)
        return 2

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"  {'✅' if ok else '❌'} {name} — {detail}")
        if not ok:
            failures.append(name)

    print("[1] 읽혀야 하는 곳 — canary 가시성 (빈 배열 = 정책 누락 함정)")
    st, rows = _get("documents?title=eq.__rls_canary_rule__&select=id,title")
    check("documents(rule canary)", st == 200 and bool(rows),
          f"status={st} rows={len(rows or [])}")

    st, rows = _get("sections?breadcrumb=like.__rls_canary_rule__*&select=id")
    check("sections(rule canary)", st == 200 and bool(rows),
          f"status={st} rows={len(rows or [])}")

    st, rows = _get("chunks?text=eq.rls canary rule chunk&select=id")
    check("chunks(rule canary)", st == 200 and bool(rows),
          f"status={st} rows={len(rows or [])}")

    st, rows = _get("article_registry?article_title=eq.canary&select=article_no")
    check("article_registry(canary)", st == 200 and bool(rows),
          f"status={st} rows={len(rows or [])}")

    st, rows = _get("hotline_config_public?key=eq.rls_canary&select=key,value")
    check("hotline_config_public(canary)", st == 200 and bool(rows),
          f"status={st} rows={len(rows or [])}")

    print("[2] 막혀야 하는 곳 — source_type·비공개 테이블 (행이 보이면 노출 사고)")
    st, rows = _get("documents?title=eq.__rls_canary_report__&select=id")
    check("documents(report 차단)", not rows, f"status={st} rows={len(rows or [])}")

    st, rows = _get("chunks?text=eq.rls canary report chunk&select=id")
    check("chunks(report 차단)", not rows, f"status={st} rows={len(rows or [])}")

    for table in ("eval_runs", "boost_rules", "pinned_citations", "query_traces",
                  "faq_cache", "synonym_dictionary", "critical_keywords",
                  "hotline_config"):
        st, rows = _get(f"{table}?select=*&limit=1")
        check(f"{table}(비공개)", not rows, f"status={st} rows={len(rows or [])}")

    print("[3] anon 쓰기 거부")
    st = _post("query_traces", {
        "query_id": "rls_verify_probe", "stage": "intake",
        "started_at": "2026-01-01T00:00:00Z", "ok": True,
    })
    check("query_traces INSERT 거부", st in (401, 403, 404), f"status={st}")

    print()
    if failures:
        print(f"FAIL — {len(failures)}건: {', '.join(failures)}")
        return 1
    print("PASS — RLS 정책 전 항목 의도대로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
