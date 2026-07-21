"""small-to-big 근사 — 검색 hit 청크에 같은 문서 chunk_idx ±radius 이웃을
런타임 결합해 합성 컨텍스트를 만든다 (ADR-8 완화 지시 1: DB 변경 없음).

v1 스키마엔 section 계층이 없으므로(보류), "부모 section 전체" 대신
이웃 창(window)이 그 근사다. SELECT 전용 — 쓰기 없음.

실패는 fail-open (원본 chunks 그대로 반환) + stderr 기록 — 검색 결과를
이웃 결합 실패로 잃는 것이 더 나쁘다. silent 는 아니다.
"""
from __future__ import annotations

import sys
from typing import Any

from .stages import RetrievedChunk


def expand_with_neighbors(
    supabase: Any,
    chunks: list[RetrievedChunk],
    *,
    radius: int = 2,
) -> list[RetrievedChunk]:
    """각 hit 의 text 를 [idx-radius, idx+radius] 이웃 결합 텍스트로 교체.

    RPC 반환에는 chunk_idx 가 없으므로 hit id 로 1회 조회 후, 문서별로
    필요한 idx 만 IN 조회한다 (hit 수 k 기준 쿼리 1 + 문서 수 ≤ k).
    """
    if not chunks or radius <= 0:
        return chunks
    try:
        ids = [c["chunk_id"] for c in chunks if c.get("chunk_id")]
        idx_rows = (
            supabase.table("nexus_chunks")
            .select("id, document_id, chunk_idx")
            .in_("id", ids)
            .execute()
            .data or []
        )
        idx_by_id = {str(r["id"]): r for r in idx_rows}

        # 문서별 필요 idx 집합
        wanted: dict[str, set[int]] = {}
        for c in chunks:
            row = idx_by_id.get(str(c.get("chunk_id")))
            if row is None or row.get("chunk_idx") is None:
                continue
            i = int(row["chunk_idx"])
            doc = str(row["document_id"])
            wanted.setdefault(doc, set()).update(
                range(max(0, i - radius), i + radius + 1)
            )

        # 문서별 이웃 텍스트 로드
        text_by_doc_idx: dict[tuple[str, int], str] = {}
        for doc, idxs in wanted.items():
            rows = (
                supabase.table("nexus_chunks")
                .select("document_id, chunk_idx, text")
                .eq("document_id", doc)
                .in_("chunk_idx", sorted(idxs))
                .execute()
                .data or []
            )
            for r in rows:
                if r.get("chunk_idx") is not None:
                    text_by_doc_idx[(str(r["document_id"]), int(r["chunk_idx"]))] = (
                        r.get("text") or ""
                    )

        out: list[RetrievedChunk] = []
        for c in chunks:
            row = idx_by_id.get(str(c.get("chunk_id")))
            if row is None or row.get("chunk_idx") is None:
                out.append(c)  # idx 미상 — 원본 유지
                continue
            i = int(row["chunk_idx"])
            doc = str(row["document_id"])
            window = [
                text_by_doc_idx[(doc, j)]
                for j in range(max(0, i - radius), i + radius + 1)
                if (doc, j) in text_by_doc_idx and text_by_doc_idx[(doc, j)]
            ]
            merged = dict(c)
            merged["text"] = "\n".join(window) if window else c["text"]
            out.append(merged)  # type: ignore[arg-type]
        return out
    except Exception as e:
        print(
            f"[neighbors] FAILED (fail-open, 원본 유지): {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return chunks
