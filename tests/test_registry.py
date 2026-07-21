"""파생 원장(registry.build_ledger) 계약 — 오프라인 (DB 없음).

핵심: article_no 컬럼이 아니라 text 재추출로 원장이 만들어지고,
조의N 이 붕괴 없이 보존되며, §5 verify 3분기가 결정론으로 동작한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compass_engine.registry import build_ledger  # noqa: E402

DOCS = [
    {"id": "d1", "title": "(CSR) 대외출강 운영 지침"},
    {"id": "d2", "title": "(공통) 임직원 징계기준"},
]

CHUNKS = [
    # v1 파서 결함 시나리오: article_no 컬럼은 붕괴값("제3조")이지만
    # text 에는 제3조의2 가 있다 — 원장은 text 만 믿어야 한다.
    {"document_id": "d1", "text": "제3조의2(외부 강의 사전승인) …", "article_no": "제3조"},
    {"document_id": "d1", "text": "제1조(목적) 이 지침은 …"},
    {"document_id": "d2", "text": "부칙 제2조(경과조치) …"},
    {"document_id": "d2", "text": "조항 표기가 없는 서문 텍스트"},
]


def _ledger():
    return build_ledger(CHUNKS, DOCS)


def test_ledger_extracts_from_text_not_column():
    lg = _ledger()
    assert lg.has_article("d1", "제3조의2")      # text 재추출 — 조의2 보존
    assert not lg.has_article("d1", "제3조")     # 붕괴값(컬럼)은 원장에 없다


def test_ledger_addendum_and_counts():
    lg = _ledger()
    assert lg.has_article("d2", "부칙 제2조")
    assert lg.chunk_rows_scanned == 4
    assert lg.has_document_title("(CSR) 대외출강 운영 지침")


def test_verify_three_way():
    lg = _ledger()
    assert lg.verify("(CSR) 대외출강 운영 지침", "제3조의2") == "ok"
    assert lg.verify("(CSR) 대외출강 운영 지침", "제99조") == "article_missing"
    assert lg.verify("(없는 문서)", "제1조") == "document_missing"
    assert lg.verify("(공통) 임직원 징계기준", None) == "ok"  # 문서 단위 인용
