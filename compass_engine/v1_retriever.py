"""v1 RPC 래퍼 리트리버 — nexus_hybrid_search_v3_pgroonga 를 그대로 호출 (ADR-8).

Retriever 프로토콜(stages.py) 구현체. eval 하니스와 (Phase 1 의) 정본
파이프라인이 같은 구현을 쓴다 — v1 의 retrieve_for_eval 우회 함수 안티패턴 제거.

payload 는 v1 core/retriever.py 호출부 미러: match_count=top_k,
rrf_k=60, pool_size=max(30, top_k*6). SELECT/RPC 전용 — 쓰기 없음.

RPC 반환 article_no 는 v1 파서 산출물이라 조의N 붕괴 가능성이 있다 —
표시용 참고로만 정규화해 싣고(§5 원장 대조 키는 registry 가 text 재추출로
직접 만든다), 정규화 실패 시 None.
"""
from __future__ import annotations

from typing import Any, Callable

from .articles import parse_article_ref
from .stages import IntakeResult, RetrievedChunk, RetrieveResult, RouteResult

_RPC_NAME = "nexus_hybrid_search_v3_pgroonga"

EmbedFn = Callable[[str], list[float]]


def gemini_embed_fn() -> EmbedFn:
    """기본 임베더 (Gemini 768) — GEMINI_API_KEY 환경변수 필요.

    v1 core/embedder.embed_one 과 동일 API 계열. 다른 임베더로 A/B 하려면
    V1RpcRetriever(embed_fn=...) 로 주입한다 (ADR-4: env 추상화 유지).
    """
    import os
    from google import genai  # 지연 import — 오프라인 환경 고려

    key = os.environ.get("GEMINI_API_KEY") or ""
    if not key:
        raise RuntimeError("GEMINI_API_KEY 미설정 — v1 RPC 리트리버는 질의 임베딩이 필요")
    cli = genai.Client(api_key=key)

    def _embed(text: str) -> list[float]:
        res = cli.models.embed_content(
            model="gemini-embedding-001", contents=text,
            config={"task_type": "RETRIEVAL_QUERY", "output_dimensionality": 768},
        )
        return list(res.embeddings[0].values)

    return _embed


class V1RpcRetriever:
    """v1 하이브리드 검색 RPC 래퍼. supabase 는 .rpc(name, payload).execute()
    를 제공하는 클라이언트(supabase-py anon 키)면 된다.

    rpc_name: "nexus_hybrid_search_v3_pgroonga"(기본, v1 embedding) 또는
              "nexus_hybrid_search_v4_ctx"(contextual — ctx_embedding).
              두 함수는 시그니처 동일 → eval A/B 가 rpc_name 만 바꾼다.
    expand_neighbors: small-to-big 근사 — hit 청크에 chunk_idx ±radius
              이웃을 런타임 결합 (ADR-8 완화 지시 1)."""

    def __init__(self, supabase: Any, embed_fn: EmbedFn, *, top_k: int = 3,
                 rpc_name: str = _RPC_NAME,
                 expand_neighbors: bool = True, neighbor_radius: int = 2):
        self._sb = supabase
        self._embed = embed_fn
        self.top_k = top_k
        self.rpc_name = rpc_name
        self.expand_neighbors = expand_neighbors
        self.neighbor_radius = neighbor_radius

    def retrieve(self, intake: IntakeResult, route: RouteResult) -> RetrieveResult:
        q = intake["masked_text"]
        embedding = self._embed(q)
        payload = {
            "query_embedding": embedding,
            "query_text": q,
            "match_count": self.top_k,
            "rrf_k": 60,
            "pool_size": max(30, self.top_k * 6),
        }
        rows = self._sb.rpc(self.rpc_name, payload).execute().data or []
        chunks: list[RetrievedChunk] = []
        for r in rows:
            title = str(r.get("doc_title") or "")
            ref = parse_article_ref(str(r.get("article_no") or ""))
            canonical = ref.canonical if ref else None
            chunks.append(RetrievedChunk(
                chunk_id=str(r.get("id") or ""),
                section_id="",                       # v1 스키마엔 section 계층 없음 (ADR-8 보류)
                document_id=str(r.get("document_id") or ""),
                source_type="rule",
                breadcrumb=f"{title}>{canonical}" if canonical else title,
                article_no=canonical,
                text=str(r.get("text") or ""),
                score=float(r.get("rrf_score") or 0.0),
            ))
        if self.expand_neighbors and chunks:
            from .neighbors import expand_with_neighbors
            chunks = expand_with_neighbors(
                self._sb, chunks, radius=self.neighbor_radius,
            )
        provider = f"v1-rpc:{self.rpc_name}" + (
            "+neighbors" if self.expand_neighbors else ""
        )
        return RetrieveResult(chunks=chunks, query_set=[q], provider=provider)
