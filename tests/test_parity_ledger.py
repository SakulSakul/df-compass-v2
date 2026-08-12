"""파리티 원장 게이트 (지시서 002-A).

원장 규칙 (원장 CSV 헤더 주석에도 동일 명기):
- 모든 행은 disposition 값을 가져야 한다 — 미처분(공란) 0 을 테스트가 강제.
- 허용 처분: PORTED / SEMANTIC / EXCLUDED / IMPLEMENT / PENDING.
- IMPLEMENT 는 구현 완료 시 해당 커밋에서 PORTED 로 갱신한다 — IMPLEMENT
  잔존 0 이 게이트 조건 (구현 없이 처분만 바꾸는 것 금지: 커밋 diff 로 감리).
- '#' 로 시작하는 행은 주석.

원장 정본은 감리자 생성 — CSV 미수신 상태에서는 skip 으로 표시된다
(통과 위장 금지: skip 사유가 테스트 출력에 남는다).
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

LEDGER = Path(__file__).resolve().parent.parent / "docs" / "parity-ledger.csv"
ALLOWED = {"PORTED", "SEMANTIC", "EXCLUDED", "IMPLEMENT", "PENDING"}


def _rows() -> list[dict]:
    with open(LEDGER, encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


@pytest.mark.skipif(not LEDGER.exists(),
                    reason="파리티 원장 CSV 미수신 (감리자 릴레이 대기) — 002-A 블로커")
def test_ledger_every_row_disposed():
    rows = _rows()
    assert rows, "원장이 비어 있음"
    undisposed = [r for r in rows if not (r.get("disposition") or "").strip()]
    assert undisposed == [], f"미처분 항목 {len(undisposed)}건"
    bad = [r for r in rows
           if r["disposition"].strip().upper() not in ALLOWED]
    assert bad == [], f"허용 외 처분 값 {len(bad)}건"


@pytest.mark.skipif(not LEDGER.exists(),
                    reason="파리티 원장 CSV 미수신 (감리자 릴레이 대기) — 002-A 블로커")
def test_ledger_no_implement_left():
    """IMPLEMENT 잔존 0 — 구현 완료분은 같은 커밋에서 PORTED 로 갱신."""
    left = [r for r in _rows()
            if r["disposition"].strip().upper() == "IMPLEMENT"]
    assert left == [], f"IMPLEMENT 잔존 {len(left)}건: " + \
        ", ".join((r.get("item") or "?") for r in left)
