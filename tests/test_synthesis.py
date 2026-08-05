"""synthesis — 오프라인 (주입형 gen_fn): 계약 검사·fallback·no-silent."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import pytest
from compass_engine.synthesis import (
    check_section_contract, synthesize, SYSTEM_CONTRACT,
)

_GOOD = ("질문하신 내용: 'x'\n\n**핵심 결론**\n가능합니다.\n\n"
         "**📋 사규 기준**\n((재무) 법인카드 관리 지침) 근거.\n\n"
         "**권장 행동**\n경리팀 문의.\n\n[참조: (재무) 법인카드 관리 지침]")


def test_contract_check():
    assert check_section_contract(_GOOD) is True
    assert check_section_contract("핵심 결론만 있음") is False
    assert check_section_contract("사규에서 확인되지 않는 내용입니다.") is True  # 면제


def test_primary_path():
    r = synthesize("q", [], primary=lambda s, u: _GOOD, fallback=None)
    assert r.used_fallback is False and r.section_contract_ok is True
    assert r.provider.startswith("gemini:")


def test_fallback_path():
    def boom(s, u):
        raise RuntimeError("primary down")
    r = synthesize("q", [], primary=boom, fallback=lambda s, u: _GOOD)
    assert r.used_fallback is True and r.provider.startswith("claude:")


def test_both_fail_raises():
    def boom(s, u):
        raise RuntimeError("down")
    with pytest.raises(RuntimeError):
        synthesize("q", [], primary=boom, fallback=None)


# ── R3 g02 무결성 게이트 (오프라인 — fake GenFn) ─────────────────
def test_gate_retries_once_and_flags_integrity():
    from compass_engine.synthesis import synthesize
    calls = []
    def bad_gen(system, user):
        calls.append(1)
        return "핵심 결론 없음 — 절단된 답변"
    r = synthesize("q", [], primary=bad_gen, fallback=None)
    assert len(calls) == 2 and r.retries == 1
    assert r.integrity_ok is False

def test_gate_passes_contract_answer_first_try():
    from compass_engine.synthesis import synthesize
    good = ("질문하신 내용\n**핵심 결론**\nx\n**권장 행동**\ny\n[참조: 문서]")
    r = synthesize("q", [], primary=lambda s, u: good, fallback=None)
    assert r.integrity_ok is True and r.retries == 0

def test_gate_oos_answer_exempt():
    from compass_engine.synthesis import synthesize
    oos = "사규에서 확인되지 않는 내용입니다. 담당 부서에 문의해 주세요."
    r = synthesize("q", [], primary=lambda s, u: oos, fallback=None)
    assert r.integrity_ok is True and r.retries == 0
