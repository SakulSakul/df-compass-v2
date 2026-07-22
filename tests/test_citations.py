"""§5 인용 추출·대조(citations.check_citations) — 오프라인.

계약: 실재쌍 ok / 비실재 조항 article_missing / 비실재 문서 document_missing /
미귀속 unattributed, 조의2 정규형 유지, has_fabrication 플래그.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compass_engine.citations import check_citations, summarize_checks  # noqa: E402
from compass_engine.registry import build_ledger  # noqa: E402

LEDGER = build_ledger(
    chunk_rows=[
        {"document_id": "d1", "text": "제3조의2(사전승인) … 제5조(신고) …"},
        {"document_id": "d2", "text": "제1조(목적) …"},
    ],
    document_rows=[
        {"id": "d1", "title": "(CSR) 대외출강 운영 지침"},
        {"id": "d2", "title": "(공통) 임직원 징계기준"},
    ],
)


def test_ok_pair_and_uije2():
    ans = "외부 강의는 사전 승인 대상입니다 ((CSR) 대외출강 운영 지침, 제3조의2)."
    cs = check_citations(ans, LEDGER)
    assert len(cs) == 1
    assert cs[0].verdict == "ok" and cs[0].canonical == "제3조의2"


def test_article_missing_is_fabrication():
    ans = "근거는 ((CSR) 대외출강 운영 지침, 제99조) 입니다."
    cs = check_citations(ans, LEDGER)
    assert cs[0].verdict == "article_missing"
    assert summarize_checks(cs)["has_fabrication"] is True


def test_document_missing_unknown_title():
    ans = "관련 규정은 (가공의 유령 지침, 제2조) 참조."
    cs = check_citations(ans, LEDGER)
    assert cs[0].verdict == "document_missing"


def test_unattributed_ref():
    ans = "일반적으로 제7조에 따라 처리합니다."
    cs = check_citations(ans, LEDGER)
    assert cs[0].verdict == "unattributed"


def test_multi_pairs_summary():
    ans = ("((공통) 임직원 징계기준, 제1조)에 따라 징계하며, "
           "((CSR) 대외출강 운영 지침, 제5조)도 함께 봅니다. "
           "그리고 (없는 문서, 제3조)는 위조입니다.")
    s = summarize_checks(check_citations(ans, LEDGER))
    assert s["total"] == 3 and s["ok"] == 2
    assert s["document_missing"] == 1 and s["has_fabrication"] is True


def test_prefix_stripped_title_resolves():
    # "(인사) X" 를 "X" 로 인용해도 실재 문서로 해석 (유일 매칭 시)
    from compass_engine.registry import build_ledger
    lg = build_ledger(
        [{"document_id": "d9", "text": "제9조(신고) …"}],
        [{"id": "d9", "title": "(인사) 직장 내 괴롭힘 예방·대응지침"}],
    )
    cs = check_citations("(직장 내 괴롭힘 예방·대응지침, 제9조)에 따라 신고.", lg)
    assert cs[0].verdict == "ok" and cs[0].title.startswith("(인사)")
