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
- 각 발췌 표제 아래의 〔인용 지침〕을 그대로 따른다.
- 조항 번호 인용은 해당 발췌의 '인용 가능 조항' 목록에 있는 번호만 쓴다.
  목록에 없는 조번호는 어떤 경우에도 쓰지 않는다 (추측·창작·인접 조 대체 금지).
- 〔조번호 표기 금지〕 문서는 (문서명, "섹션 제목") 형식으로만 인용한다 —
  본문의 항목 번호(예: 4.1, 11.)를 '제4조' 같은 조번호로 바꿔 쓰지 않는다.
- 법령(…법·…시행령·…에 관한 규칙 등) 조항은 발췌 본문에 그 표기가 그대로
  있을 때만 복사해 쓴다. 발췌에 없는 법령 조항을 지어내지 않는다.
- 근거를 서술하는 문장에는 출처 표기를 붙인다: 조문형은 (문서명, 제N조),
  그 외는 (문서명). 라벨을 붙일 수 있는 곳에서 출처 생략 금지.
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
    input_chars: int = 0   # wave 1 계측 — user 프롬프트 길이 (합성 입력 토큰 프록시)
    # R3 wave A — g02 무결성 게이트 (합성 절단 재발 계열 차단)
    finish_reason: str = "STOP"   # primary/fallback 최종 응답의 종료 사유
    integrity_ok: bool = True     # 계약 충족 여부 (재합성 1회 후에도 미충족이면 False)
    retries: int = 0              # 게이트 재합성 횟수


GenFn = Callable[[str, str], str]   # (system, user) -> answer


class TruncatedCompletion(RuntimeError):
    """finish_reason != STOP — 합성 절단 (R3 g02 게이트: fallback 으로 구제)."""


def _gemini_gen(system: str, user: str) -> str:
    from google import genai
    cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("NEXUS_CHAT_MODEL", "gemini-3.6-flash")
    res = cli.models.generate_content(
        model=model, contents=user,
        config={"system_instruction": system, "temperature": 0.0,
                "max_output_tokens": 4096},
    )
    fr = ""
    try:
        fr = str(res.candidates[0].finish_reason.name)  # type: ignore[union-attr]
    except Exception:
        fr = ""
    if fr and fr != "STOP":
        raise TruncatedCompletion(f"finish_reason={fr}")
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


def _citation_directive(c: RetrievedChunk, anchor_map: dict | None) -> str:
    """청크별 〔인용 지침〕 (wave 2 합성 계약 — 앵커 사전 주입).

    조문형: 이 발췌 본문에 실재 + 원장 등재 조번호만 나열 (발명·인접 대체 차단).
    C-class: 조번호 표기 금지 명시 (아라비아 항목 번호의 제N조 변환 차단).
    anchor_map 미주입(플래그 off·어블레이션) 시 빈 문자열 — 기존 프롬프트와 동일.
    """
    if not anchor_map:
        return ""
    from .anchors import chunk_citable_anchors
    title = c["breadcrumb"].split(">")[0]
    doc = anchor_map.get(title)
    if doc is None:
        return ""
    if doc.doc_class == "article":
        citable = chunk_citable_anchors(c["text"], doc)
        if citable:
            return f"\n〔인용 지침: 인용 가능 조항 = {', '.join(citable)} — 이 목록의 번호만〕"
        return "\n〔인용 지침: 이 발췌에는 인용 가능한 조번호 없음 — 문서명으로만 인용〕"
    return "\n〔인용 지침: 조번호 표기 금지 문서 — (문서명, \"섹션 제목\") 으로 인용〕"


def build_user_prompt(question: str, chunks: Sequence[RetrievedChunk],
                      anchor_map: dict | None = None) -> str:
    ctx = "\n\n".join(
        f"[{c['breadcrumb']}]{_citation_directive(c, anchor_map)}\n{c['text'][:2500]}"
        for c in chunks
    ) or "(검색 결과 없음)"
    return f"[질문]\n{question}\n\n[사규 발췌]\n{ctx}"


def synthesize(question: str, chunks: Sequence[RetrievedChunk], *,
               anchor_map: dict | None = None,
               primary: GenFn = _gemini_gen,
               fallback: GenFn | None = _claude_gen) -> SynthesisResult:
    """합성 1회 — primary 실패 시 fallback, 둘 다 실패 시 raise (no silent).

    anchor_map: anchors.build_anchor_map(ledger) — 주입 시 청크별 인용 지침
    활성 (플래그 NEXUS_ENABLE_CITATION_CONTRACT 는 호출부에서 제어).

    R3 g02 무결성 게이트: 절단(finish_reason != STOP)은 예외로 승격돼
    fallback(Claude) 강제. 생성 후 계약 미충족(섹션 계약 위반 또는 [참조:]
    푸터 부재 — OOS 무응답은 면제)이면 재합성 1회, 재실패 시
    integrity_ok=False 로 반환 (verify 가 degrade 격상 — R2 심의 의결).
    """
    def _gen_once() -> tuple[str, str, bool]:
        try:
            return (primary(SYSTEM_CONTRACT, user),
                    f"gemini:{os.environ.get('NEXUS_CHAT_MODEL', 'gemini-3.6-flash')}",
                    False)
        except Exception as e:
            print(f"[synthesis] primary FAILED → fallback: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            if fallback is None:
                raise
            return (fallback(SYSTEM_CONTRACT, user),
                    f"claude:{os.environ.get('NEXUS_FALLBACK_MODEL', 'claude-haiku-4-5-20251001')}",
                    True)

    def _contract_met(ans: str) -> bool:
        if any(m in ans for m in _OOS_MARKERS):
            return True                      # 무응답 표명은 푸터 면제
        return check_section_contract(ans) and "[참조:" in ans

    user = build_user_prompt(question, chunks, anchor_map)
    t0 = time.perf_counter()
    answer, provider, used_fallback = _gen_once()
    retries = 0
    if not _contract_met(answer):
        print("[synthesis:gate] 계약 미충족 → 재합성 1회", file=sys.stderr, flush=True)
        retries = 1
        answer2, provider2, fb2 = _gen_once()
        if _contract_met(answer2):
            answer, provider, used_fallback = answer2, provider2, fb2
    integrity = _contract_met(answer)
    if not integrity:
        print("[synthesis:gate] 재합성 후에도 미충족 — integrity_ok=False (degrade 격상 예정)",
              file=sys.stderr, flush=True)
    return SynthesisResult(
        answer_md=answer, provider=provider, used_fallback=used_fallback,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        section_contract_ok=check_section_contract(answer),
        input_chars=len(user),
        finish_reason="STOP", integrity_ok=integrity, retries=retries,
    )
