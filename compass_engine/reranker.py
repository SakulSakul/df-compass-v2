"""리랭커 — v1 nexus_reranker(listwise·JSON) 이식 (Phase 1 ④).

모델: env NEXUS_RERANK_MODEL (기본 gemini-3.5-flash-lite — 2026-07-21 A/B 로
확정) + NEXUS_RERANK_THINKING (기본 "minimal"; 3.5 계열은 thinking_budget
구식 파라미터를 400 으로 거부 — thinking_level 사용, 프로브로 확정).

계약:
- rerank(question, chunks) → 재정렬된 chunks (원소 불변, 순서만).
- 실패는 fail-open(원 순서) + stderr + failures 카운터 — silent 금지.
- retrieve 스테이지 내부 부품이므로 Retriever 프로토콜은 불변 —
  V1RpcRetriever 가 pool 확장 후 본 모듈로 재정렬해 top_k 컷.

eval/rerank_ab.py(계측용)와 동일 프롬프트·파싱 — 계측기와 정본의 드리프트 방지.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Callable, Sequence

from .stages import RetrievedChunk

RerankFn = Callable[[str, Sequence[RetrievedChunk]], list[RetrievedChunk]]

_PROMPT = """사규 검색 결과를 질문 관련도 순으로 재정렬하세요.

[질문]
{q}

[후보 청크]
{items}

JSON only: {{"order": [가장 관련 높은 것부터 후보 번호 나열]}}"""


class GeminiReranker:
    """listwise 재정렬 — 확정 기본값: 3.5-flash-lite + thinking_level minimal."""

    def __init__(self, model: str | None = None, thinking_level: str | None = None):
        self.model = model or os.environ.get(
            "NEXUS_RERANK_MODEL", "gemini-3.5-flash-lite")
        self.thinking_level = (thinking_level
                               or os.environ.get("NEXUS_RERANK_THINKING", "minimal"))
        self.latencies_ms: list[float] = []
        self.failures = 0
        from google import genai
        self._cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def __call__(self, question: str,
                 chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        chunks = list(chunks)
        if len(chunks) < 2:
            return chunks
        items = "\n".join(f"{i}. [{c['breadcrumb']}] {c['text'][:300]}"
                          for i, c in enumerate(chunks))
        cfg: dict = {"temperature": 0.0, "max_output_tokens": 256,
                     "response_mime_type": "application/json"}
        if self.thinking_level:
            cfg["thinking_config"] = {"thinking_level": self.thinking_level}
        t0 = time.perf_counter()
        try:
            res = self._cli.models.generate_content(
                model=self.model, contents=_PROMPT.format(q=question, items=items),
                config=cfg)
            self.latencies_ms.append((time.perf_counter() - t0) * 1000)
            m = re.search(r"\{.*\}", getattr(res, "text", "") or "", re.DOTALL)
            order = json.loads(m.group(0))["order"] if m else []
            picked, seen = [], set()
            for idx in order:
                if isinstance(idx, int) and not isinstance(idx, bool) \
                        and 0 <= idx < len(chunks) and idx not in seen:
                    seen.add(idx)
                    picked.append(chunks[idx])
            for i, c in enumerate(chunks):     # 응답 누락분 원 순서 보충
                if i not in seen:
                    picked.append(c)
            return picked
        except Exception as e:
            self.latencies_ms.append((time.perf_counter() - t0) * 1000)
            self.failures += 1
            print(f"[reranker] FAILED ({self.model}): {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            return chunks                       # fail-open — 원 순서
