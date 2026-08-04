"""DF COMPASS v2 · 사용자용 UI (Phase 2 — 컷오버 전제 정비).

정본 파이프라인 배선(엔진 무변경): intake(critical 게이트·pii) →
retrieve(v4-ctx + rerank + 이웃결합) → synthesize(섹션 계약, 3.6 확정) →
verify(§5 결정론) → render.

안전 표면 불변 조건 (위반 시 H 정지 — STATUS.md 백로그 항목 참조):
- verify action=block 이면 답변을 내보내지 않는다 (품질 서열 1위).
- verify action=degrade 이면 ⚠ 신뢰도 강등 칩을 답변 위에 표출.
- critical 이면 배너 + enforce_structure(4단 + 핫라인 박스).
렌더는 단일 경로(_render_assistant)로 통일 — 위 로직이 한 곳에만 존재한다.

디자인: v1 Warm Editorial 완전 이식 (ui/styles.py 토큰·챗 카드·다크 말풍선·
critical 인버티드 블록·브랜드/디스클레이머·히어로 — v2 표면에 해당하는 전량).

secrets/env: SUPABASE_URL, SUPABASE_KEY(anon), GEMINI_API_KEY
(원장 로드는 anon SELECT — RLS 미부여 시 service key 를 SUPABASE_SERVICE_KEY 로)
"""
from __future__ import annotations

import os
import sys
import time

import streamlit as st

st.set_page_config(page_title="DF COMPASS", page_icon="🧭", layout="wide")

# ── Warm Editorial (v1 ui/styles.py 이식 — v2 표면 해당분 전량) ──
_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

:root {
  /* warm editorial — accent 레드·font Pretendard, 뉴트럴은 웜 톤 (v1 동일) */
  --c-primary:    #1F1E1D;
  --c-accent:     #C8102E;
  --c-accent-dark:#9A0C24;
  --c-accent-bg:  #FCEBEE;
  --c-text:     #3D3C38;
  --c-caption:  #87867F;
  --c-muted:    #B5B3A9;
  --c-border:   #E8E6DC;
  --c-surface:  #FAF9F5;
  --c-bg:       #F5F4ED;
  --font: 'Pretendard', -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
}

/* ── Reset ── */
html, body, .stApp {
  font-family: var(--font) !important;
  background: var(--c-bg) !important;
  color: var(--c-text) !important;
}
#MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
* { box-sizing: border-box; }

/* 헤더 anchor 링크 제거 (v1 동일) */
.stMarkdown h1 > a, .stMarkdown h2 > a, .stMarkdown h3 > a,
h1 > a.anchor-link, h2 > a.anchor-link, h3 > a.anchor-link { display: none !important; }

/* ── 4px top frame (신세계 시그니처 레드) ── */
.nx-topbar {
  position: fixed; top: 0; left: 0; right: 0; height: 4px;
  background: var(--c-accent); z-index: 9999;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--c-surface) !important;
  border-right: 1px solid var(--c-border) !important;
}
[data-testid="stSidebar"] > div { background: transparent !important; }
[data-testid="stSidebar"] hr {
  border: none !important;
  border-top: 1px solid var(--c-border) !important;
  margin: 20px 0 !important;
}
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"] {
  position: fixed !important; top: 12px !important; left: 12px !important;
  z-index: 999999 !important; width: 44px !important; height: 44px !important;
  background: #ffffff !important; border: 1.5px solid #1A1A1A !important;
  border-radius: 6px !important; box-shadow: 0 2px 6px rgba(0,0,0,0.08) !important;
  align-items: center !important; justify-content: center !important;
}

.nx-brand { padding: 28px 0 20px; border-bottom: 2px solid #1A1A1A; margin-bottom: 24px; }
.nx-brand-eyebrow {
  font-size: 10px; font-weight: 700; letter-spacing: 0.3em;
  text-transform: uppercase; color: #AEAEAE; margin: 0 0 6px;
}
.nx-brand-title { font-size: 20px; font-weight: 700; color: #1A1A1A; letter-spacing: -0.01em; margin: 0; }
.nx-disclaimer { font-size: 11px; color: #AEAEAE; line-height: 1.65; margin: 0; }

/* ── Main ── */
[data-testid="stMain"] { background: var(--c-bg) !important; }
[data-testid="block-container"] { padding-top: 2rem !important; }

/* Hero (빈 홈) */
.nx-hero { padding: 48px 0 40px; border-bottom: 1px solid #E0E0E0; margin-bottom: 40px; }
.nx-hero-eyebrow {
  font-size: 11px; font-weight: 700; letter-spacing: 0.3em;
  text-transform: uppercase; color: var(--c-accent); margin: 0 0 16px;
}
.nx-hero-title {
  font-size: 36px; font-weight: 700; color: #1A1A1A;
  letter-spacing: -0.02em; line-height: 1.15; margin: 0 0 14px;
}
.nx-hero-title::after { content: "."; color: var(--c-accent); margin-left: 1px; }
.nx-hero-sub { font-size: 14px; color: #767676; line-height: 1.7; margin: 0; font-weight: 400; }

/* ── Chat messages — 줄 길이 제한 + 흰 카드 (v1 동일) ── */
[data-testid="stChatMessage"] {
  max-width: 880px;
  margin-left: auto;
  margin-right: auto;
  border: 1px solid var(--c-border) !important;
  border-radius: 16px !important;
  padding: 1.25rem 1.5rem !important;
  margin-bottom: 0.6rem !important;
  background: #FFFFFF !important;
  box-shadow: 0 1px 3px rgba(31,30,29,0.05) !important;
}
[data-testid="stChatMessage"] .stMarkdown { max-width: 840px; }
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"] {
  background-color: #f1f3f5 !important;
  border: 1px solid #e5e8eb !important;
}
/* user 질문 — 오른쪽 다크 말풍선 + 아바타 숨김 (v1 동일) */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: #2C2B28 !important;
  border-color: #2C2B28 !important;
  width: fit-content !important;
  max-width: 78% !important;
  margin-left: auto !important;
  margin-right: 0 !important;
  padding: 0.7rem 1.1rem !important;
  border-radius: 16px !important;
  box-shadow: 0 1px 3px rgba(31,30,29,0.12) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="chatAvatarIcon-user"] { display: none !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown li,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown p,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown li {
  color: #FFFFFF !important;
  max-width: none !important;
}

/* ── Chat input (v1 동일 — 흰색·플랫) ── */
[data-testid="stChatInput"] textarea {
  font-family: var(--font) !important;
  border: 0 !important;
  border-top: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  background: #fff !important;
  font-size: 14.5px !important;
  line-height: 1.6 !important;
  min-height: 54px !important;
  padding: 14px 16px !important;
  color: var(--c-text) !important;
  box-shadow: none !important;
  outline: none !important;
  resize: none !important;
}
[data-testid="stChatInput"] textarea:focus { border-top: 1px solid var(--c-border) !important; box-shadow: none !important; }
[data-testid="stChatInput"] {
  border: 0 !important;
  border-top: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: #fff !important;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] [data-testid="stChatInputTextArea"] { background: #fff !important; }
[data-testid="stBottomBlockContainer"] { padding-top: 0.5rem !important; padding-bottom: 0.6rem !important; }

/* ── 버튼 (예시 질문) — v1 default 버튼 문법 ── */
.stButton > button {
  font-family: var(--font) !important;
  background: var(--c-bg) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  color: var(--c-primary) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  padding: 0.75rem 1rem !important;
  text-align: left !important;
  white-space: normal !important;
  height: auto !important;
  line-height: 1.6 !important;
  box-shadow: none !important;
}
.stButton > button:hover {
  background: var(--c-surface) !important;
  border-color: var(--c-primary) !important;
  transform: none !important;
}

/* ── Expander · Alert · LinkButton · Caption (v1 동일) ── */
[data-testid="stExpander"] {
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  background: var(--c-bg) !important;
  box-shadow: none !important;
  margin-top: 12px !important;
}
[data-testid="stExpander"] summary {
  font-family: var(--font) !important;
  font-size: 11px !important;
  font-weight: 700 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  color: var(--c-caption) !important;
}
[data-testid="stAlert"] { border-radius: 0 !important; box-shadow: none !important; font-family: var(--font) !important; }
[data-testid="stLinkButton"] > a {
  font-family: var(--font) !important;
  background: var(--c-primary) !important;
  border: 1px solid var(--c-primary) !important;
  border-radius: 0 !important;
  color: #FFFFFF !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  letter-spacing: 0.05em !important;
  box-shadow: none !important;
}
[data-testid="stLinkButton"] > a:hover { background: #333333 !important; border-color: #333333 !important; }
.stCaption { font-family: var(--font) !important; font-size: 11px !important; color: var(--c-caption) !important; }

/* ── Critical alert — 인버티드 블록 + 좌측 4px 레드 (v1 .nx-critical) ── */
.nx-critical {
  background: #1A1A1A;
  color: #FFFFFF;
  border-left: 4px solid var(--c-accent);
  padding: 12px 18px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}
.nx-critical-label {
  font-size: 10px; font-weight: 700; letter-spacing: 0.2em;
  background: #FFFFFF; color: #1A1A1A; padding: 2px 6px; flex-shrink: 0;
}

/* ── 신뢰도 강등 칩 (안전 표면 — 가시성 유지) ── */
.nx-chip-warn {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  border-radius: 6px;
  padding: 3px 10px;
  margin-bottom: 8px;
  background: var(--c-accent-bg);
  color: #8A1020;
  border: 1px solid var(--c-accent);
}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)
st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)

_EXAMPLES = (
    "법인카드 사용 기준이 어떻게 되나요?",
    "협력사에서 선물을 받았는데 어떻게 해야 하나요?",
    "국내 출장 시 숙박비 한도가 궁금합니다.",
)

_BLOCK_MESSAGE = ("이 답변은 비실재 문서 인용이 감지되어 차단되었습니다. "
                  "질문을 바꿔 다시 시도하거나 담당 부서에 문의해 주세요.")


@st.cache_resource(show_spinner="준비 중…")
def _engine():
    from supabase import create_client
    from compass_engine.anchors import build_anchor_map
    from compass_engine.registry import load_ledger
    from compass_engine.reranker import GeminiReranker
    from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn
    from compass_engine.v1port.config import load_hotlines

    url = os.environ["SUPABASE_URL"]
    anon = os.environ.get("SUPABASE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    sb = create_client(url, anon)
    ledger_key = os.environ.get("SUPABASE_SERVICE_KEY") or anon
    ledger = load_ledger(create_client(url, ledger_key))
    # wave 3 보장 계층 (심의 확정 예산) — 플래그 off 시 종전 동결 구성
    if os.environ.get("NEXUS_ENABLE_GUARANTEE_LAYER", "true").lower() == "true":
        from compass_engine.doc_router import DocRouter
        retriever = V1RpcRetriever(
            sb, gemini_embed_fn(), top_k=5,
            rpc_name="nexus_hybrid_search_v4_ctx",
            expand_neighbors=True, neighbor_radius=1,
            reranker=GeminiReranker(), rerank_pool=25,
            router=DocRouter(sb), reserved_seats=2,
            proxy_quota=1, chunk_cap=8,
        )
    else:
        retriever = V1RpcRetriever(
            sb, gemini_embed_fn(), top_k=3,
            rpc_name="nexus_hybrid_search_v4_ctx",
            expand_neighbors=True, reranker=GeminiReranker(),
        )
    # wave 2 합성 계약 — 앵커 사전 (플래그 off 면 None → 기존 프롬프트)
    anchor_map = (build_anchor_map(ledger)
                  if os.environ.get("NEXUS_ENABLE_CITATION_CONTRACT",
                                    "true").lower() == "true" else None)
    return sb, ledger, retriever, load_hotlines(sb), anchor_map


def _sidebar(hotlines: dict) -> None:
    with st.sidebar:
        st.markdown(
            '<div class="nx-brand">'
            '<p class="nx-brand-eyebrow">윤리·컴플라이언스 AI 챗봇</p>'
            '<p class="nx-brand-title">🧭 DF COMPASS</p></div>',
            unsafe_allow_html=True)
        with st.expander("ℹ️ DF COMPASS 안내", expanded=False):
            st.markdown(
                "**DF COMPASS** — 디에프 컴파스\n\n"
                "신세계디에프 사규를 근거와 함께 안내하는 AI 챗봇입니다. "
                "일하다 마주치는 윤리·컴플라이언스 질문에 사규 발췌를 "
                "바탕으로 답해 드립니다.\n\n"
                "\"COMPASS(나침반)\"라는 이름처럼, 임직원이 바른 방향을 "
                "잡을 수 있도록 곁에서 길을 안내하는 도구를 지향합니다.\n\n"
                "본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다. "
                "인사 행정 사항은 인사교육팀에 직접 문의하세요.")
        url = hotlines.get("ethics_hotline_url") or hotlines.get("internal_report_url")
        if url:
            st.link_button("신세계면세점 핫라인 제보하기", url,
                           use_container_width=True)
        st.markdown("---")
        st.markdown(
            '<p class="nx-disclaimer">'
            "본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다.<br>"
            "신고·조사 사항은 CSR팀 또는 신세계면세점 핫라인으로,<br>"
            "인사 규정·복리후생 등 인사 행정 사항은 인사교육팀으로 "
            "문의해 주시기 바랍니다.</p>",
            unsafe_allow_html=True)


def _render_assistant(entry: dict) -> None:
    """안전 표면 단일 렌더 경로 — 불변 조건은 전부 이 함수 안에 있다.

    ① blocked → 답변 미표출 + 차단 안내 (verify block)
    ② critical → 배너 + (enforce_structure 된) 답변
    ③ degrade → ⚠ 신뢰도 강등 칩 + 답변
    """
    if entry.get("blocked"):
        st.error(_BLOCK_MESSAGE)
        return
    if entry.get("critical"):
        st.markdown(
            '<div class="nx-critical"><span class="nx-critical-label">'
            "CRITICAL</span>심각 사안 감지 — 핫라인 우선 안내가 포함됩니다. "
            "실제 응급상황은 즉시 핫라인을 이용하세요.</div>",
            unsafe_allow_html=True)
    if entry.get("degraded"):
        st.markdown('<span class="nx-chip-warn">⚠ 인용 일부 미검증 — '
                    "신뢰도 강등</span>", unsafe_allow_html=True)
    st.markdown(entry["answer"])


def _ask(question: str) -> dict:
    """정본 파이프라인 1턴 실행 → 히스토리 엔트리 (엔진 무변경 배선)."""
    from compass_engine.intake import run_intake
    from compass_engine.synthesis import synthesize
    from compass_engine.v1port.critical_mode import enforce_structure
    from compass_engine.verify import verify_answer

    sb, ledger, retriever, hotlines, anchor_map = _engine()
    t0 = time.perf_counter()
    intake = run_intake(sb, question)
    res = retriever.retrieve(intake, {"tracks": ["rule"], "intent": "ui"})
    syn = synthesize(intake["masked_text"], res["chunks"], anchor_map=anchor_map)
    verdict = verify_answer(syn.answer_md, ledger)

    if intake["is_critical"]:
        answer = enforce_structure(
            base_answer=syn.answer_md, kind=intake["critical_kind"] or "safety",
            action_items=None, hotlines=hotlines)
    else:
        answer = syn.answer_md

    # trace — 로컬 stderr (ADR-8: DB 쓰기 금지). 화면 노출 없음.
    print(f"[ui:trace] q_len={len(question)} critical={intake['is_critical']} "
          f"chunks={len(res['chunks'])} action={verdict['action']} "
          f"grade={verdict['grade']} "
          f"elapsed={time.perf_counter()-t0:.1f}s", file=sys.stderr, flush=True)

    blocked = verdict["action"] == "block"
    return {
        "role": "assistant",
        "answer": "" if blocked else answer,   # block 답변은 저장조차 안 함
        "blocked": blocked,
        "critical": bool(intake["is_critical"]),
        "degraded": verdict["action"] == "degrade",
    }


# ── 페이지 조립 ──────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []

try:
    _hotlines = _engine()[3]
except Exception:
    _hotlines = {}
_sidebar(_hotlines)

# chat_input 은 하단 고정 위젯이라 위치 무관 — 먼저 읽어 히어로 조건에 반영
question = st.chat_input("사규에 대해 물어보세요")
if not question:
    question = st.session_state.pop("pending_q", None)

if not st.session_state["messages"] and not question:
    st.markdown(
        '<div class="nx-hero">'
        '<p class="nx-hero-eyebrow">Ethics · Compliance</p>'
        '<p class="nx-hero-title">사규, 물어보면 바로 나침반</p>'
        '<p class="nx-hero-sub">신세계디에프 사규를 근거와 함께 안내합니다. '
        "아래 예시를 누르거나 자유롭게 질문해 보세요.</p></div>",
        unsafe_allow_html=True)
    cols = st.columns(len(_EXAMPLES))
    for i, (col, ex) in enumerate(zip(cols, _EXAMPLES)):
        if col.button(ex, key=f"ex_{i}", use_container_width=True):
            st.session_state["pending_q"] = ex
            st.rerun()

for m in st.session_state["messages"]:
    if m["role"] == "user":
        with st.chat_message("user"):
            st.markdown(m["content"])
    else:
        with st.chat_message("assistant", avatar="🧭"):
            _render_assistant(m)

if question:
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🧭"):
        with st.spinner("사규를 확인하고 답변을 작성하는 중…"):
            entry = _ask(question)
        _render_assistant(entry)
    st.session_state["messages"].append(entry)
