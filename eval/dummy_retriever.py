"""더미 Retriever — 하니스 완주 검증 전용 (Phase 0).

실 검색 품질과 무관하다. 목적은 두 가지뿐:
1. eval 하니스가 엔진 계약(Retriever 프로토콜)만으로 끝까지 도는지 증명.
2. Phase 1 실 RAG retriever 가 도착하면 같은 하니스에 꽂아 A/B 하는 자리 확보.

키워드 겹침 점수(결정론) — LLM/DB/네트워크 없음.
"""
from __future__ import annotations

from compass_engine.stages import (
    IntakeResult, RetrievedChunk, RetrieveResult, RouteResult,
)

# (문서 제목, 트리거 키워드) — v1 사규 제목 축약형. 품질 주장 아님.
_DUMMY_DOCS: list[tuple[str, list[str]]] = [
    ("(총무) 출장비 지급 지침", ["출장", "출장비", "숙박", "일비"]),
    ("(재무) 법인카드 관리지침", ["법인카드", "카드", "한도"]),
    ("(안전) 위험성평가 운영 규정", ["위험성평가", "위험성", "안전"]),
    ("(정보보안) 개인정보 보호 지침", ["개인정보", "정보유출", "유출"]),
    ("(CSR) 성희롱 예방 지침", ["성희롱", "괴롭힘"]),
    ("(CSR) 대외출강 운영 지침", ["대외출강", "강의", "강의료", "인터뷰", "리서치", "사례"]),
    ("(공통) 임직원 징계기준", ["징계", "위반", "처벌"]),
    ("(총무) 회의실 운영 기준", ["회의실"]),
]


class DummyRetriever:
    """키워드 겹침 top-k. 겹침 0 문서는 반환하지 않는다 (negative fixture 대응)."""

    def __init__(self, top_k: int = 3):
        self.top_k = top_k

    def retrieve(self, intake: IntakeResult, route: RouteResult) -> RetrieveResult:
        q = intake["masked_text"]
        scored: list[tuple[float, str]] = []
        for title, kws in _DUMMY_DOCS:
            score = sum(1.0 for k in kws if k in q)
            if score > 0:
                scored.append((score, title))
        scored.sort(key=lambda t: (-t[0], t[1]))
        chunks: list[RetrievedChunk] = [
            RetrievedChunk(
                chunk_id=f"dummy-{i}", section_id=f"dummy-sec-{i}",
                document_id=f"dummy-doc-{i}", source_type="rule",
                breadcrumb=f"{title}>제1조", article_no="제1조",
                text=f"{title} 더미 본문", score=score,
            )
            for i, (score, title) in enumerate(scored[: self.top_k])
        ]
        return RetrieveResult(
            chunks=chunks, query_set=[q], provider="dummy-keyword-overlap",
        )
