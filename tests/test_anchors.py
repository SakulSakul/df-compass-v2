"""앵커 사전·법령 태깅(anchors.py) + 합성 계약 주입 — 오프라인 (wave 2 + A1)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from compass_engine.anchors import (
    DocAnchors, build_anchor_map, chunk_citable_anchors, find_law_ref_starts,
    is_law_ref)
from compass_engine.registry import build_ledger
from compass_engine.synthesis import build_user_prompt

LEDGER = build_ledger(
    [{"document_id": "d1", "text": "제3조(승인) … 제5조(신고) … 부칙"},
     {"document_id": "d2", "text": "1. 목적 … 4.1 행위 금지 … 부칙"}],
    [{"id": "d1", "title": "(CSR) 대외출강 운영 지침"},
     {"id": "d2", "title": "(인사) 직장 내 괴롭힘 예방·대응지침"}],
)


def test_build_anchor_map_classes():
    am = build_anchor_map(LEDGER)
    d1 = am["(CSR) 대외출강 운영 지침"]
    assert d1.doc_class == "article" and d1.anchors == {"제3조", "제5조"}
    d2 = am["(인사) 직장 내 괴롭힘 예방·대응지침"]
    assert d2.doc_class == "cclass" and d2.anchors == frozenset()  # 부칙만 → C-class


def test_law_ref_tagging():
    t = ("산업안전보건법 제128조의2 와 산업안전보건기준에 관한 규칙 제79조, "
         "그리고 (CSR) 대외출강 운영 지침 제3조.")
    starts = find_law_ref_starts(t)
    assert len(starts) == 2                       # 법령 2건만
    art_pos = t.index("제3조")
    assert not is_law_ref(t, art_pos)             # 사규 조항은 법령 아님


def test_law_tail_does_not_match_rule_titles():
    # '기준'·'규칙' 단독 어미는 법령으로 보지 않는다 — 징계기준 오태깅 방지
    t = "임직원 징계기준 제3조에 따른다."
    assert find_law_ref_starts(t) == set()


def test_chunk_citable_anchors_intersection():
    doc = DocAnchors(doc_class="article", anchors=frozenset({"제3조", "제5조"}))
    # 청크 본문에 제3조·제9조 표기 — 원장 등재 교집합인 제3조만 인용 가능
    assert chunk_citable_anchors("제3조(승인) … 제9조(기타) …", doc) == ["제3조"]
    # 법령 조항은 사규 앵커 후보에서 제외
    assert chunk_citable_anchors("산업안전보건법 제3조 참조", doc) == []


def test_prompt_directive_injection():
    am = build_anchor_map(LEDGER)
    chunks = [
        {"chunk_id": "c1", "section_id": "", "document_id": "d1",
         "source_type": "rule", "breadcrumb": "(CSR) 대외출강 운영 지침>제3조",
         "article_no": "제3조", "text": "제3조(승인) 내용", "score": 1.0},
        {"chunk_id": "c2", "section_id": "", "document_id": "d2",
         "source_type": "rule", "breadcrumb": "(인사) 직장 내 괴롭힘 예방·대응지침",
         "article_no": None, "text": "4.1 행위 금지", "score": 0.9},
    ]
    p = build_user_prompt("q", chunks, build_anchor_map(LEDGER))
    assert "인용 가능 조항 = 제3조" in p
    assert "조번호 표기 금지 문서" in p
    # 미주입(어블레이션) 시 지침 없음 — 기존 프롬프트와 동일
    p0 = build_user_prompt("q", chunks, None)
    assert "인용 지침" not in p0
