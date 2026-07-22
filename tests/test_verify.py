"""§5 검증기(verify_answer) — 오프라인. 3분기 action·confidence·계약 검사."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from compass_engine.registry import build_ledger
from compass_engine.verify import verify_answer

LEDGER = build_ledger(
    [{"document_id": "d1", "text": "제3조의2(사전승인) … 제5조(신고) …"}],
    [{"id": "d1", "title": "(CSR) 대외출강 운영 지침"}],
)
_SECTIONS = ("\n\n**핵심 결론**\nx\n\n**권장 행동**\ny\n\n[참조: (CSR) 대외출강 운영 지침]")


def test_pass_on_real_citation():
    r = verify_answer("((CSR) 대외출강 운영 지침, 제3조의2) 근거." + _SECTIONS, LEDGER)
    assert r["action"] == "pass" and r["confidence"] == 1.0
    assert r["section_contract_ok"] is True


def test_degrade_on_article_missing():
    r = verify_answer("((CSR) 대외출강 운영 지침, 제99조) 근거." + _SECTIONS, LEDGER)
    assert r["action"] == "degrade"
    assert r["confidence"] == 0.0


def test_block_on_document_missing():
    r = verify_answer("(유령 지침, 제2조) 근거." + _SECTIONS, LEDGER)
    assert r["action"] == "block"


def test_no_citation_low_confidence_but_pass():
    r = verify_answer("근거 없이 서술만." + _SECTIONS, LEDGER)
    assert r["action"] == "pass" and r["confidence"] == 0.0


def test_block_wins_over_degrade():
    ans = ("((CSR) 대외출강 운영 지침, 제99조) 와 (유령 지침, 제1조) 인용." + _SECTIONS)
    assert verify_answer(ans, LEDGER)["action"] == "block"
