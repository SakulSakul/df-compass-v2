"""앵커 사전 + 외부 법령 인용 태깅 (wave 2 + 승인 수정 A1).

앵커 사전: 파생 원장(registry)에서 문서별 "인용 가능 앵커 집합"을 파생한다.
- 조문형(article): 실조항(제N조/제N조의M) 이 원장에 1건 이상 등재된 문서.
- C-class(cclass): 실조항 0건 (부칙·별표류뿐이거나 무등재) — 조번호 인용
  자체가 성립하지 않는 문서 (G2 실측 76/101).
합성 계약과 verify 가 이 사전 하나를 공유한다 (드리프트 방지).

법령 앵커 클래스 (A1, 감리자 확정 규칙):
(a) 법령명+조번호 패턴으로 사규 앵커와 구분 태깅
(b) verify 원장 대조 제외 — 검증 불가이지 위조가 아니다
(c) conf 중립 — HIGH 원료 금지, 사규 앵커 0 + 법령만이면 UNVERIFIED
(d) 합성 계약 동일 원칙 — 투입 청크 실재분만 복사
법령 판정은 보수적이다: '…법 / …법률 / …시행령 / …시행규칙 / …에 관한
규칙 / 헌법' 어미가 조번호 직전(≤30자)에 선행할 때만. '규칙'·'기준' 단독
어미는 사규 제목과 겹치므로 법령으로 보지 않는다 (임직원 징계기준 등 오태깅
방지). 회귀 케이스: g27 "산업안전보건법 제128조의2"·"산업안전보건기준에
관한 규칙 제79조".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .articles import find_article_refs

# 실조항 판정 — canonical 형태 기준 (compare_matrix._REAL_ARTICLE 과 동일 골격)
_REAL_ARTICLE = re.compile(r"제\d+조(의\d+)?$")

# 법령명 어미 — 조번호 직전 텍스트 꼬리에 대해 판정 (보수적 명단)
_LAW_TAIL = re.compile(
    r"([가-힣0-9·\s]{1,30}?(?:법|법률|기본법|시행령|시행규칙|헌법)"
    r"|[가-힣0-9·\s]{1,30}?에\s?관한\s?규칙)\s*(?:」|\))?\s*$"
)
_LAW_WINDOW = 30


@dataclass(frozen=True)
class DocAnchors:
    doc_class: str              # "article" | "cclass"
    anchors: frozenset[str]     # 인용 가능 canonical 집합 (cclass 는 빈 집합)


def build_anchor_map(ledger: Any) -> dict[str, DocAnchors]:
    """원장 → {문서 제목: DocAnchors}. active 문서 전수 (읽기 파생, DB 쓰기 없음)."""
    out: dict[str, DocAnchors] = {}
    for title, doc_id in ledger.title_to_doc_id.items():
        arts = ledger.articles_by_doc.get(doc_id) or set()
        real = frozenset(a for a in arts if _REAL_ARTICLE.fullmatch(str(a)))
        out[title] = DocAnchors(
            doc_class="article" if real else "cclass", anchors=real)
    return out


def is_law_ref(text: str, ref_start: int) -> bool:
    """조번호(ref_start 위치)가 외부 법령 귀속인지 — 직전 꼬리 텍스트로 판정."""
    head = text[max(0, ref_start - _LAW_WINDOW):ref_start]
    return bool(_LAW_TAIL.search(head))


def find_law_ref_starts(text: str) -> set[int]:
    """텍스트 내 법령 귀속 조번호 참조의 시작 위치 집합 (태깅·감사용)."""
    return {start for _ref, start, _end in find_article_refs(text)
            if is_law_ref(text, start)}


def chunk_citable_anchors(chunk_text: str, doc: DocAnchors) -> list[str]:
    """합성 계약용 — 투입 청크 본문에 실재하고 원장에도 등재된 조번호만.

    (심의 4항: 조문형 문서는 '투입 청크 실재 조번호만' 인용 — 발명·추론 금지.
    법령 귀속 조번호는 사규 앵커 후보에서 제외 — A1(d) 는 별도 규칙으로 안내)
    """
    if doc.doc_class != "article":
        return []
    seen: list[str] = []
    for ref, start, _end in find_article_refs(chunk_text):
        if is_law_ref(chunk_text, start):
            continue
        if ref.canonical in doc.anchors and ref.canonical not in seen:
            seen.append(ref.canonical)
    return seen
