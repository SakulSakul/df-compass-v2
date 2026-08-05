"""doc_router — 질의→지배문서 라우팅 (wave 3 보장 계층, 심의 1항).

카탈로그 소스: nexus_documents(title, auto_keywords, auto_query_examples)
SELECT — A2 사전 검증(2026-08-04)에서 이 소스로 골든 히트율 46/46(100%),
confident 44/46 실측. 홀드아웃 표현은 카탈로그·프롬프트에 수록 금지(봉인
규칙) — 카탈로그는 DB 값만 쓰므로 구조적으로 준수된다.

불변식 (add-only): 라우팅 실패·저확신·파싱 실패는 전부 no-op
({"doc_titles": [], "confident": False}) — 라우터가 현행보다 나쁜 결과를
만들 수 없다. 예외는 삼키지 않고 stderr 기록 (silent 금지).

eval/router_probe.py(A2 계측)와 이 모듈이 동일 카탈로그·프롬프트를 쓴다 —
계측기와 정본의 드리프트 방지 (probe 가 본 모듈을 import).
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

ROUTER_MODEL_ENV = "NEXUS_ROUTER_MODEL"
_DEFAULT_MODEL = "gemini-3.6-flash"

PROMPT = """당신은 사규 문서 라우터입니다. 아래 [문서 카탈로그]에서 사용자
질문을 지배하는(가장 직접 규정하는) 문서를 고르세요.

[질문]
{q}

[문서 카탈로그]
{catalog}

JSON only: {{"docs": ["<정확한 문서 제목>", "<정확한 문서 제목>", "<정확한 문서 제목>"], "confident": true|false}}
- docs 는 관련 순 최대 3개, 카탈로그의 제목을 그대로 복사.
- 확실히 지배 문서를 특정할 수 없으면 confident=false."""


def build_catalog(sb: Any) -> tuple[str, dict[str, str]]:
    """카탈로그 텍스트 + {title: document_id}. active 문서 전수 (SELECT 전용)."""
    rows = (sb.table("nexus_documents")
            .select("id,title,auto_keywords,auto_query_examples")
            .eq("status", "active").execute().data or [])
    lines, title_to_id = [], {}
    for r in sorted(rows, key=lambda x: x["title"]):
        kw = ", ".join((r.get("auto_keywords") or [])[:8])
        ex = " / ".join((r.get("auto_query_examples") or [])[:2])
        lines.append(f"- {r['title']}" + (f" | 키워드: {kw}" if kw else "")
                     + (f" | 예시: {ex}" if ex else ""))
        title_to_id[r["title"]] = str(r["id"])
    return "\n".join(lines), title_to_id


class DocRouter:
    """LLM 라우터 — 기동 시 카탈로그 1회 로드, 질의당 1콜."""

    def __init__(self, sb: Any, *, model: str | None = None):
        self.model = model or os.environ.get(ROUTER_MODEL_ENV, _DEFAULT_MODEL)
        self.catalog, self.title_to_id = build_catalog(sb)
        from google import genai
        self._cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def route(self, question: str) -> dict:
        """→ {"doc_titles": [실재 제목 ≤2], "confident": bool}. 실패는 no-op."""
        try:
            res = self._cli.models.generate_content(
                model=self.model,
                contents=PROMPT.format(q=question, catalog=self.catalog),
                config={"temperature": 0.0, "max_output_tokens": 1024,
                        "response_mime_type": "application/json",
                        "thinking_config": {"thinking_level": "minimal"}})
            m = re.search(r"\{.*\}", getattr(res, "text", "") or "", re.DOTALL)
            d = json.loads(m.group(0)) if m else {}
            # R1 보정 (R3 wave C): top-2 → top-3 — CSR경영방침류 포괄 방침
            # 미스(g03·g08·g13) 완화. 카탈로그·예약석(2석)은 불변 — 최소 침습.
            titles = [t for t in (d.get("docs") or [])[:3]
                      if t in self.title_to_id]      # 카탈로그 실재 제목만
            return {"doc_titles": titles, "confident": bool(d.get("confident"))}
        except Exception as e:
            print(f"[doc_router] FAILED (no-op): {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            return {"doc_titles": [], "confident": False}
