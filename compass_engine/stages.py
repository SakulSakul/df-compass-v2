"""스테이지 typed 입출력 + trace 레코드 계약 [DESIGN.md §2 — Phase 0 뼈대].

추상화 상한(설계서 명시): retrieve 스테이지만 교체형 인터페이스.
나머지 스테이지는 typed dict 계약뿐 — 클래스 계층·플러그인 구조 금지.

G1 미통과(2026-07-21)로 rule 트랙은 RAG 확정 — CAG 구현은 만들지 않는다.
단 Retriever 프로토콜(교체형)은 유지: 미래 재심의 롤백 구조이자 eval A/B 전제.

대화 상태(§3): 모호성 되묻기·후보선택은 2턴 이상을 요구하므로 직전 되묻기와
사용자 선택을 포함한 대화 이력이 intake·route 입력에 포함된다.
query_traces 는 감사 로그이지 대화 상태 저장소가 아니다.
"""
from __future__ import annotations

from typing import Literal, Protocol, TypedDict


SourceType = Literal["rule", "skill", "report", "code"]
Track = Literal["rule", "skill", "report", "code"]


# ── 대화 상태 (intake·route 입력의 일부) ─────────────────────────
class ConversationTurn(TypedDict):
    role: Literal["user", "assistant"]
    text: str
    # 직전 턴이 모호성 되묻기였다면 그 되묻기 종류와 사용자가 고른 후보
    disambiguation: dict | None


class EngineQuery(TypedDict):
    """엔진 진입점 입력 — UI·eval CLI·MCP 가 동일하게 만든다."""
    query_id: str
    raw_text: str
    history: list[ConversationTurn]  # 빈 리스트 허용 (1턴 질의)


# ── [1] intake ───────────────────────────────────────────────────
class IntakeResult(TypedDict):
    masked_text: str                  # PII 마스킹 적용 후
    is_critical: bool                 # critical 게이트 — True 면 핫라인 연결 최우선
    critical_matches: list[str]
    oos: bool                         # out-of-scope 라우팅
    faq_hit_id: str | None            # FAQ 캐시 적중 (verify 이전 유일한 답변 경로)
    ambiguity: dict | None            # 되묻기·후보선택·multi-facet 판정


# ── [2] route ────────────────────────────────────────────────────
class RouteResult(TypedDict):
    tracks: list[Track]               # 기본 ["rule"], 명시적일 때만 추가
    intent: str


# ── [3] retrieve — 유일한 교체형 인터페이스 ──────────────────────
class RetrievedChunk(TypedDict):
    chunk_id: str
    section_id: str
    document_id: str
    source_type: SourceType
    breadcrumb: str                   # "문서명>제3장>제12조"
    article_no: str | None            # 정규형 (articles.canonical)
    text: str
    score: float


class RetrieveResult(TypedDict):
    chunks: list[RetrievedChunk]      # 검색은 chunk, LLM 컨텍스트는 부모 section(§3)
    query_set: list[str]              # 원 쿼리 불가침 + multi-query 확장분
    provider: str                     # 구현 식별자 (eval A/B 비교 축)


class Retriever(Protocol):
    """retrieve 스테이지 교체형 인터페이스 — CAG vs RAG 를 동일 testset 으로
    A/B 하는 구조적 전제이자, 게이트/Kill criteria 롤백을 '설정 변경'으로 만드는 장치."""

    def retrieve(self, intake: IntakeResult, route: RouteResult) -> RetrieveResult: ...


# ── [4] verify ───────────────────────────────────────────────────
class CitationCheck(TypedDict):
    document_title: str
    article_no: str | None            # 정규형
    verdict: Literal["ok", "article_missing", "document_missing"]


class VerifyResult(TypedDict):
    citations: list[CitationCheck]    # §5 결정론 검증 — article_registry 대조
    section_contract_ok: bool
    confidence: float                 # 멀티시그널 산출 (Phase 1)
    action: Literal["pass", "degrade", "block", "route_to_department"]


# ── [5] render ───────────────────────────────────────────────────
class RenderResult(TypedDict):
    answer_md: str
    citations: list[CitationCheck]
    confidence_chip: str
    followups: list[str]              # grounded 후속질문


# ── trace — 전 스테이지 기록 (no-silent-except) ──────────────────
class TraceRecord(TypedDict):
    query_id: str
    stage: Literal["intake", "route", "retrieve", "verify", "render"]
    started_at: str                   # ISO8601
    duration_ms: int
    ok: bool
    error: str | None                 # 실패는 반드시 기록 — silent fail 금지 (CLAUDE.md E)
    circuit: dict                     # 헬퍼 fail-open 회로 상태 (helper_health)
    payload: dict                     # 스테이지 입출력 요약 (PII 마스킹 후)
