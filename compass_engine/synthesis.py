"""섹션 계약 합성 — Phase 1 ⑤ (DESIGN §2 [3b]·§8).

v1 prompts 의 섹션 계약을 미러: 질문 확인 → 핵심 결론 → 📋 사규 기준 →
⚖️ 징계 기준(해당 시) → 권장 행동 → [참조: …] 통합 출처.
critical 변형·칩·SUGGESTIONS 는 ⑧·⑨ 범위 — 여기 없음.

인용 원칙 (golden 교훈 2026-07-22): 발췌에 조항 번호가 명시된 경우에만
(문서명, 제N조), 아니면 문서명만. 발췌 밖 내용 금지("확인 필요").

Provider: Gemini primary (env NEXUS_CHAT_MODEL, 기본 gemini-3.6-flash —
2026-07-22 채택 확정) / Claude fallback (ANTHROPIC_API_KEY 있을 때).
둘 다 실패 시 raise — 결정적 거절(answer_guard)은 ⑧ 에서 앞단에 선다.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from .stages import RetrievedChunk

SYSTEM_CONTRACT = """당신은 신세계디에프 사규 안내 챗봇 DF COMPASS 입니다.
아래 [사규 발췌]만 근거로 답하며, 반드시 다음 섹션 구조로 출력합니다.

질문하신 내용: '<질문 요지 한 줄>'

**핵심 결론**
<가능/불가/조건부 등 결론 1~3문장>

**📋 사규 기준**
<근거 내용 요약 — 각 근거에 인라인 인용>

**⚖️ 징계 기준** (징계·제재 관련 근거가 발췌에 있을 때만 이 섹션 포함)
<해당 내용>

**권장 행동**
<사용자가 할 일. 문의 부서는 발췌 본문에 명시된 부서명 그대로 — 임의 변환 금지>

[참조: <문서명>, <문서명>, ...]

인용 규칙 (모든 섹션과 [참조:] 블록에 동일 적용 — 반드시 준수):
- 발췌 표제([문서명>조항])나 본문에 조항 번호가 **그대로 보이는 경우에만**
  그 번호로 (문서명, 제N조) 인용. 보이지 않으면 **문서명만** — 인라인이든
  [참조:] 블록이든 조항 번호를 추측·창작하지 않는다.
- 발췌에 없는 내용은 지어내지 말고 "확인 필요"로 표시.
- 질문이 사규와 무관하면 섹션 구조 대신 "사규에서 확인되지 않는 내용"임을
  밝히고 담당 창구 문의를 안내."""

# 섹션 계약 검사(결정론) — verify 스테이지의 section_contract_ok 가 소비.
_REQUIRED_MARKERS = ("핵심 결론", "권장 행동", "[참조:")
_OOS_MARKERS = ("사규에서 확인되지 않", "확인되지 않는", "확인할 수 없")


def check_section_contract(answer: str) -> bool:
    """필수 섹션 존재 여부. 무관-질문 답변(무응답 표명)은 계약 면제."""
    if any(m in answer for m in _OOS_MARKERS):
        return True
    return all(m in answer for m in _REQUIRED_MARKERS)


@dataclass
class SynthesisResult:
    answer_md: str
    provider: str          # "gemini:<model>" | "claude:<model>"
    used_fallback: bool
    elapsed_ms: int
    section_contract_ok: bool


GenFn = Callable[[str, str], str]   # (system, user) -> answer


def _gemini_gen(system: str, user: str) -> str:
    from google import genai
    cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("NEXUS_CHAT_MODEL", "gemini-3.6-flash")
    res = cli.models.generate_content(
        model=model, contents=user,
        config={"system_instruction": system, "temperature": 0.0,
                "max_output_tokens": 4096},
    )
    return getattr(res, "text", "") or ""


def _claude_gen(system: str, user: str) -> str:
    import anthropic
    cli = anthropic.Anthropic()
    model = os.environ.get("NEXUS_FALLBACK_MODEL", "claude-haiku-4-5-20251001")
    msg = cli.messages.create(
        model=model, max_tokens=4096, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def build_user_prompt(question: str, chunks: Sequence[RetrievedChunk]) -> str:
    ctx = "\n\n".join(
        f"[{c['breadcrumb']}]\n{c['text'][:2500]}" for c in chunks
    ) or "(검색 결과 없음)"
    return f"[질문]\n{question}\n\n[사규 발췌]\n{ctx}"


def synthesize(question: str, chunks: Sequence[RetrievedChunk], *,
               primary: GenFn = _gemini_gen,
               fallback: GenFn | None = _claude_gen) -> SynthesisResult:
    """합성 1회 — primary 실패 시 fallback, 둘 다 실패 시 raise (no silent)."""
    user = build_user_prompt(question, chunks)
    t0 = time.perf_counter()
    try:
        answer = primary(SYSTEM_CONTRACT, user)
        provider = f"gemini:{os.environ.get('NEXUS_CHAT_MODEL', 'gemini-3.6-flash')}"
        used_fallback = False
    except Exception as e:
        print(f"[synthesis] primary FAILED → fallback: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        if fallback is None:
            raise
        answer = fallback(SYSTEM_CONTRACT, user)
        provider = f"claude:{os.environ.get('NEXUS_FALLBACK_MODEL', 'claude-haiku-4-5-20251001')}"
        used_fallback = True
    return SynthesisResult(
        answer_md=answer, provider=provider, used_fallback=used_fallback,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        section_contract_ok=check_section_contract(answer),
    )
