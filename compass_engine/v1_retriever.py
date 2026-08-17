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
                 expand_neighbors: bool = True, neighbor_radius: int = 2,
                 reranker: Any = None, rerank_pool: int = 15,
                 router: Any = None, reserved_seats: int = 2,
                 proxy_quota: int | None = None, chunk_cap: int | None = None):
        self._sb = supabase
        self._embed = embed_fn
        self.top_k = top_k
        self.rpc_name = rpc_name
        self.expand_neighbors = expand_neighbors
        self.neighbor_radius = neighbor_radius
        # Phase 1 ④: reranker(question, chunks)->chunks 주입 시 RRF pool 을
        # rerank_pool 로 확장해 재정렬 후 top_k 컷 (v1 top-15 선례).
        self.reranker = reranker
        self.rerank_pool = rerank_pool
        # wave 3 보장 계층 (심의 1·2항) — 전부 미지정이면 기존 동작과 동일
        # (add-only 불변식: 라우팅 실패·저확신은 no-op).
        self.router = router                    # DocRouter | None
        self.reserved_seats = reserved_seats    # 최종 top_k 컷 면제석 (≤2)
        self.proxy_quota = proxy_quota          # 최종 내 프록시 문서 청크 상한
        self.chunk_cap = chunk_cap              # 중복 제거 후 총 청크 상한

    @staticmethod
    def _is_proxy(c: RetrievedChunk) -> bool:
        from .proxies import PROXY_DOCS
        return c["breadcrumb"].split(">")[0] in PROXY_DOCS

    def _pick_doc_chunk(self, doc_id: str, title: str, question: str
                        ) -> RetrievedChunk | None:
        """라우팅 문서의 대표 청크 1개 — 질의 토큰 겹침 최대 (결정론 렉시컬)."""
        import re as _re
        try:
            rows = (self._sb.table("nexus_chunks")
                    .select("id,document_id,text")
                    .eq("document_id", doc_id).execute().data or [])
        except Exception:
            return None
        if not rows:
            return None
        qtok = set(_re.findall(r"[가-힣A-Za-z0-9]{2,}", question))
        best = max(rows, key=lambda r: (
            len(qtok & set(_re.findall(r"[가-힣A-Za-z0-9]{2,}", r.get("text") or ""))),
            -len(r.get("text") or "")))
        return RetrievedChunk(
            chunk_id=str(best["id"]), section_id="",
            document_id=str(best["document_id"]), source_type="rule",
            breadcrumb=title, article_no=None,
            text=str(best.get("text") or ""), score=0.0)

    def retrieve(self, intake: IntakeResult, route: RouteResult) -> RetrieveResult:
        import time
        timings: dict = {}
        q = intake["masked_text"]
        _t = time.perf_counter()
        embedding = self._embed(q)
        timings["embed_ms"] = int((time.perf_counter() - _t) * 1000)
        # Phase 1 ③: 원문을 그대로 넣으면 &@~ 가 AND 해석 → keyword leg 사망
        # (2026-07-21 A/B 에서 실측). v1 과 동일하게 OR 쿼리로 변환해 전달.
        from .pgroonga_query import build_pgroonga_query
        fetch_k = max(self.top_k, self.rerank_pool) if self.reranker else self.top_k
        payload = {
            "query_embedding": embedding,
            "query_text": build_pgroonga_query(q),
            "match_count": fetch_k,
            "rrf_k": 60,
            "pool_size": max(30, fetch_k * 6),
        }
        _t = time.perf_counter()
        rows = self._sb.rpc(self.rpc_name, payload).execute().data or []
        timings["rpc_ms"] = int((time.perf_counter() - _t) * 1000)
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
        # ── P1 계장 (지시서 010 — 관측 전용, 반환 청크·동작 무영향): 원 RRF
        # 순위는 RPC 반환 인덱스로 캡처 (라우터 풀 주입 **이전** 시점.
        # score(rrf_score) 역산 금지 — 양 leg 동점 시 비결정) ──
        _rank_trace: dict = {
            "rpc_returned": len(rows),
            "rrf_rank": {c["chunk_id"]: i + 1 for i, c in enumerate(chunks)},
        }

        # ── wave 3 보장 계층 ①: 라우팅 + 풀 주입 (rerank 전, add-only) ──
        router_hit: bool | None = None
        routed_titles: list[str] = []
        if self.router is not None:
            _t = time.perf_counter()
            r = self.router.route(q)
            timings["router_ms"] = int((time.perf_counter() - _t) * 1000)
            if r.get("confident") and r.get("doc_titles"):
                # R1 보정: 풀 주입은 라우팅 전체(≤3, add-only) — 예약석은
                # 아래 ③에서 여전히 문서 기준 최대 reserved_seats(2)만.
                routed_titles = list(r["doc_titles"])
                pool_docs = {c["document_id"] for c in chunks}
                for t in routed_titles:
                    did = self.router.title_to_id.get(t)
                    if did and did not in pool_docs:
                        inj = self._pick_doc_chunk(did, t, q)
                        if inj is not None:
                            chunks.append(inj)
                            pool_docs.add(did)
            # 저확신·무지목 → no-op (router_hit=None 유지, 기존 흐름 그대로)

        # P2′ (010-r1): 라우터 무지목 시 리랭크 스킵 — RRF 순서 그대로 top_k.
        # 근거: P1 실측 — 무관 오염(g47)과 관련 rescue(36/45)가 동일한 리랭크
        # 급상승 메커니즘이라 순위 자격 창으로 분리 불능 (심의 정본 010-r1).
        _rerank_skip = self.router is not None and not routed_titles
        if self.reranker is not None and chunks and not _rerank_skip:
            _t = time.perf_counter()
            ranked = list(self.reranker(q, chunks))
            timings["rerank_ms"] = int((time.perf_counter() - _t) * 1000)
        else:
            ranked = list(chunks)
        _rank_trace["rerank_skipped"] = _rerank_skip
        # P1 계장: 리랭크 후 순위 (라우팅 주입 청크는 rrf_rank 부재 → None 구분)
        _rank_trace["rerank_rank"] = {c["chunk_id"]: i + 1
                                      for i, c in enumerate(ranked)}

        # ── wave 3 보장 계층 ②: 프록시 감점 (결정론 stable 재정렬) ──
        if self.proxy_quota is not None:
            ranked = ([c for c in ranked if not self._is_proxy(c)]
                      + [c for c in ranked if self._is_proxy(c)])

        final = ranked[: self.top_k]

        # ── 보장 계층 ③: 예약석 — 라우팅 문서 컷 면제 (add-only 추가) ──
        if routed_titles:
            routed_ids = {self.router.title_to_id.get(t)
                          for t in routed_titles[: self.reserved_seats]}
            have = {c["document_id"] for c in final}
            for c in ranked:
                if c["document_id"] in routed_ids and c["document_id"] not in have:
                    final.append(c)
                    have.add(c["document_id"])
            router_hit = bool(routed_ids & {c["document_id"] for c in final})

        # ── 보장 계층 ④: 프록시 쿼터 (최종 내 프록시 문서 청크 ≤quota) ──
        if self.proxy_quota is not None:
            prox = [c for c in final if self._is_proxy(c)]
            if len(prox) > self.proxy_quota:
                drop_ids = {c["chunk_id"] for c in prox[self.proxy_quota:]}
                final = [c for c in final if c["chunk_id"] not in drop_ids]
                fin_ids = {c["chunk_id"] for c in final}
                for c in ranked:                      # 비프록시 후순위로 보충
                    if len(final) >= self.top_k:
                        break
                    if c["chunk_id"] not in fin_ids and not self._is_proxy(c):
                        final.append(c)
                        fin_ids.add(c["chunk_id"])

        # ── 보장 계층 ⑤: 총 청크 상한 (중복 제거 후 cap) ──
        seen_ids: set[str] = set()
        deduped: list[RetrievedChunk] = []
        for c in final:
            if c["chunk_id"] not in seen_ids:
                seen_ids.add(c["chunk_id"])
                deduped.append(c)
        if self.chunk_cap is not None:
            deduped = deduped[: self.chunk_cap]
        chunks = deduped

        if self.expand_neighbors and chunks:
            from .neighbors import expand_with_neighbors
            _t = time.perf_counter()
            chunks = expand_with_neighbors(
                self._sb, chunks, radius=self.neighbor_radius,
            )
            timings["neighbors_ms"] = int((time.perf_counter() - _t) * 1000)
        provider = f"v1-rpc:{self.rpc_name}" + (
            "+rerank" if self.reranker is not None else ""
        ) + ("+router" if self.router is not None else ""
        ) + ("+neighbors" if self.expand_neighbors else "")
        # P1 계장: 최종 컨텍스트(이웃 포함) 3층 기록 — 이웃·주입 청크는 해당
        # 층 순위 None 으로 구분
        _rank_trace["final"] = [
            {"chunk_id": c["chunk_id"],
             "doc": (c.get("breadcrumb") or "").split(">")[0],
             "rrf": _rank_trace["rrf_rank"].get(c["chunk_id"]),
             "rerank": _rank_trace["rerank_rank"].get(c["chunk_id"])}
            for c in chunks]
        res = RetrieveResult(chunks=chunks, query_set=[q], provider=provider,
                             timings=timings, router_hit=router_hit)
        res["rank_trace"] = _rank_trace   # 관측 전용 추가 키 (기존 소비처 무영향)
        return res
