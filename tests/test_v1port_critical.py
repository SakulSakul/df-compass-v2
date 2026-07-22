"""⑧ v1port critical 이식 — 오프라인 회귀 (floor·benign·4단 구조·intake 순서)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from compass_engine.intake import run_intake
from compass_engine.v1port.critical_mode import (
    CriticalDetection, detect, enforce_structure,
)
from compass_engine.v1port.pii_filter import mask_pii


class _BoomSB:
    def table(self, *_a, **_k):
        raise RuntimeError("db down")


def test_critical_floor_without_db():
    # DB 실패(빈 keywords)여도 floor 용어는 무조건 critical — v1 FMEA R2 계약
    d = detect("작업 중 중대재해가 발생하면 어떤 절차로 대응하나요?", {})
    assert d.triggered and d.kind == "safety" and d.matched == ["중대재해"]


def test_benign_stop_phrase_holds():
    d = detect("성희롱 예방 교육 절차가 어떻게 되나요?", {"harassment": ["성희롱"], "safety": []})
    assert d.triggered is False and d.matched == ["성희롱"]


def test_incident_signal_overrides_stop():
    d = detect("성희롱을 당했는데 사규에서 어떻게 처리되나요?", {"harassment": ["성희롱"], "safety": []})
    assert d.triggered is True and d.kind == "harassment"


def test_enforce_structure_four_parts():
    out = enforce_structure(base_answer="근거 답변", kind="safety",
                            action_items=None, hotlines={})
    assert all(f"### {i}." in out for i in (1, 2, 3))
    assert "📞 **핫라인 안내**" in out


def test_intake_order_and_fields():
    # DB 다운이어도 intake 는 완주(마스킹 + floor 판정) — 검색 이전 게이트 보장
    r = run_intake(_BoomSB(), "중대재해 발생 보고 010-1234-5678")
    assert r["is_critical"] is True and r["critical_kind"] == "safety"
    assert "010-1234-5678" not in r["masked_text"]  # pii 마스킹 확인
