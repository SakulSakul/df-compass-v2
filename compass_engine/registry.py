"""§5 조항 검증기의 파생 원장 — DB 테이블 없이 메모리 구축 (ADR-8).

기동 시 nexus_chunks.text 를 articles.py 단일 정규화 함수로 스캔해
(document_id, canonical 조항) 원장을 만든다.

v1 의 nexus_chunks.article_no 컬럼은 **사용 금지** — v1 파서가 "제3조의2"를
"제3조"로 붕괴시켰을 가능성이 있어(그 파서의 산출물), 원장 분모를 오염시킨다.
원문 text 재추출만이 articles.py 의 조의N 보존을 원장에 반영한다.

SELECT 전용(ADR-8): 이 모듈은 어떤 쓰기도 하지 않는다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

from .articles import extract_article_refs


@dataclass
class ArticleLedger:
    """(document_id, canonical) 존재 판정 + 문서 제목 인덱스.

    §5 결정론 검증기의 대조 원장 — LLM 판단이 아니라 조회다.
    """
    articles_by_doc: dict[str, set[str]] = field(default_factory=dict)
    title_to_doc_id: dict[str, str] = field(default_factory=dict)
    doc_id_to_title: dict[str, str] = field(default_factory=dict)
    chunk_rows_scanned: int = 0

    def has_article(self, document_id: str, canonical: str) -> bool:
        return canonical in self.articles_by_doc.get(document_id, set())

    def has_document_title(self, title: str) -> bool:
        return title in self.title_to_doc_id

    def verify(self, document_title: str, canonical: str | None) -> str:
        """§5 판정: 'ok' | 'article_missing' | 'document_missing'."""
        doc_id = self.title_to_doc_id.get(document_title)
        if doc_id is None:
            return "document_missing"
        if canonical is None:
            return "ok"  # 문서 단위 인용 (조항 미지정)
        return "ok" if self.has_article(doc_id, canonical) else "article_missing"


def build_ledger(
    chunk_rows: Iterable[dict],
    document_rows: Iterable[dict] = (),
) -> ArticleLedger:
    """원장 구축 — 순수 함수 (DB 접근 없음, 오프라인 테스트 가능).

    chunk_rows: {document_id, text} (article_no 는 있어도 읽지 않는다)
    document_rows: {id, title} (active 문서만 넘길 것 — 필터는 로더 책임)
    """
    ledger = ArticleLedger()
    for d in document_rows:
        doc_id, title = str(d.get("id") or ""), str(d.get("title") or "")
        if doc_id and title:
            ledger.title_to_doc_id[title] = doc_id
            ledger.doc_id_to_title[doc_id] = title
    for row in chunk_rows:
        doc_id = str(row.get("document_id") or "")
        text = row.get("text") or ""
        if not doc_id or not text:
            continue
        ledger.chunk_rows_scanned += 1
        refs = extract_article_refs(text)
        if refs:
            bucket = ledger.articles_by_doc.setdefault(doc_id, set())
            bucket.update(r.canonical for r in refs)
    return ledger


def load_ledger(supabase: Any, *, page_size: int = 1000) -> ArticleLedger:
    """v1 Supabase 에서 SELECT 만으로 원장 로드 (기동 시 1회).

    실패는 raise — 원장 없이 §5 검증기를 돌리는 것은 silent fail 이다
    (호출자가 명시적으로 강등을 결정해야 한다).
    """
    docs = (
        supabase.table("nexus_documents")
        .select("id, title")
        .eq("status", "active")
        .execute()
        .data or []
    )
    chunks: list[dict] = []
    offset = 0
    while True:
        page = (
            supabase.table("nexus_chunks")
            .select("document_id, text")
            .range(offset, offset + page_size - 1)
            .execute()
            .data or []
        )
        chunks.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    ledger = build_ledger(chunks, docs)
    print(
        f"[registry] ledger built: docs={len(ledger.title_to_doc_id)} "
        f"chunks_scanned={ledger.chunk_rows_scanned} "
        f"docs_with_articles={len(ledger.articles_by_doc)}",
        file=sys.stderr, flush=True,
    )
    return ledger
