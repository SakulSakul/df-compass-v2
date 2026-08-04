"""§5 검증기(verify_answer) — 오프라인. 3분기 action·grade 4등급·계약 검사.

wave 2 개정: confidence 연속값 폐기 → grade(HIGH/MEDIUM/LOW/UNVERIFIED).
pass/degrade/block 분기 자체는 불변 — 기존 케이스의 action 어서션 유지.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from compass_engine.registry import build_ledger
from compass_engine.verify import verify_answer

LEDGER = build_ledger(
    [{"document_id": "d1", "text": "제3조의2(사전승인) … 제5조(신고) …"},
     {"document_id": "d2", "text": "제1조(정신) … 제2조(행동) …"}],
    [{"id": "d1", "title": "(CSR) 대외출강 운영 지침"},
     {"id": "d2", "title": "(공통) 신세계그룹 CREDO"}],
)
_SECTIONS = ("\n\n**핵심 결론**\nx\n\n**권장 행동**\ny\n\n[참조: (CSR) 대외출강 운영 지침]")


def test_pass_on_real_citation_high():
    r = verify_answer("((CSR) 대외출강 운영 지침, 제3조의2) 근거." + _SECTIONS, LEDGER)
    assert r["action"] == "pass" and r["grade"] == "HIGH"
    assert r["section_contract_ok"] is True


def test_degrade_on_article_missing_low():
    r = verify_answer("((CSR) 대외출강 운영 지침, 제99조) 근거." + _SECTIONS, LEDGER)
    assert r["action"] == "degrade" and r["grade"] == "LOW"


def test_block_on_document_missing():
    r = verify_answer("(유령 지침, 제2조) 근거." + _SECTIONS, LEDGER)
    assert r["action"] == "block" and r["grade"] == "LOW"


def test_no_citation_unverified_but_pass():
    # 앵커 0 은 0.0 으로 뭉개지 않고 별도 상태 (심의 3항 — b군 45/52 의 처방)
    r = verify_answer("근거 없이 서술만." + _SECTIONS, LEDGER)
    assert r["action"] == "pass" and r["grade"] == "UNVERIFIED"


def test_block_wins_over_degrade():
    ans = ("((CSR) 대외출강 운영 지침, 제99조) 와 (유령 지침, 제1조) 인용." + _SECTIONS)
    assert verify_answer(ans, LEDGER)["action"] == "block"


def test_proxy_citation_caps_at_medium():
    # 프록시(CREDO) 앵커 ok 여도 HIGH 금지 — MEDIUM 상한 (심의 2·3항)
    ans = "((공통) 신세계그룹 CREDO, 제1조) 에 따라." + _SECTIONS
    r = verify_answer(ans, LEDGER)
    assert r["action"] == "pass" and r["grade"] == "MEDIUM"


def test_proxy_doc_mention_caps_high():
    # 원문 앵커 ok + 프록시 문서수준 출현 → 넓게 잡아 MEDIUM (안전 측)
    ans = ("((CSR) 대외출강 운영 지침, 제5조) 근거. (공통) 신세계그룹 CREDO 참고."
           + _SECTIONS)
    assert verify_answer(ans, LEDGER)["grade"] == "MEDIUM"


def test_law_ref_excluded_not_fabrication():
    # A1 회귀 케이스 (g27): 법령 조항은 원장 대조 제외 — 위조 아님·검증 불가
    ans = ("「(CSR) 대외출강 운영 지침」은 산업안전보건법 제128조의2 및 "
           "산업안전보건기준에 관한 규칙 제79조에 따른다." + _SECTIONS)
    r = verify_answer(ans, LEDGER)
    assert r["action"] == "pass"            # 법령 조항이 am 을 만들지 않는다
    assert r["grade"] == "UNVERIFIED"       # 사규 앵커 0 + 법령만 → UNVERIFIED (A1 c)


def test_docname_check_blocks_ghost_title():
    # wave 2 문서명 실재 검증 — 명시 인용 형식(「」)의 비실재 문서명
    ans = "「유령 관리지침」에 따르면 가능합니다." + _SECTIONS
    r = verify_answer(ans, LEDGER)
    assert r["action"] == "block"


def test_docname_check_allows_prefix_and_space_variants():
    ans = "「대외출강 운영 지침」에 따라 사전승인이 필요합니다." + _SECTIONS
    assert verify_answer(ans, LEDGER)["action"] == "pass"
