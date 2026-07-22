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
