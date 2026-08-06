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
@import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700&display=swap');

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

/* ── UI 패리티 (08-06 안건): 판정 카드 · 등급 라벨 · 출처 칩 · 베타 배너 ── */
.nx-beta {
  display: inline-block; font-size: 11px; font-weight: 600;
  color: var(--c-caption); background: var(--c-surface);
  border: 1px solid var(--c-border); border-radius: 999px;
  padding: 3px 12px; margin-left: 10px;
}
.nx-vd { margin: 2px 0 14px; }
.nx-vd-pill {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 7px 13px; border-radius: 11px; border: 1px solid var(--vd-c, #6B6A66);
  background: var(--vd-bg, #F0EFEC);
}
.nx-vd-pill .ico { width: 8px; height: 8px; border-radius: 50%;
  background: var(--vd-c, #6B6A66); flex: 0 0 8px; }
.nx-vd-pill b { font-size: 13.5px; font-weight: 700; color: var(--vd-c, #6B6A66); }
.nx-vd-quote { border-left: 3px solid var(--vd-c, #6B6A66);
  padding: 5px 0 5px 16px; margin: 12px 0 8px; }
.nx-vd-quote p { font-family: 'Nanum Myeongjo', serif; font-size: 15px;
  font-weight: 600; line-height: 1.85; color: #1F1D1A; margin: 0; }
.nx-vd-cite { display: inline-block; font-size: 11px; color: #5F5E5A;
  background: var(--c-surface); border-radius: 6px; padding: 3px 9px; margin-top: 6px; }
.nx-grade {
  display: inline-block; font-size: 12px; font-weight: 700;
  border-radius: 6px; padding: 3px 10px; margin: 0 6px 8px 0;
  border: 1px solid var(--c-border); background: var(--c-surface); color: #5F5E5A;
}
.nx-grade.high   { border-color: #2F7A4D; background: #EAF5EE; color: #2F7A4D; }
.nx-grade.medium { border-color: #B7791F; background: #FBF3E2; color: #B7791F; }
.nx-grade.unv    { border-color: var(--c-muted); background: var(--c-surface); color: #6B6A66; }
.nx-doc-chip {
  display: inline-block; font-size: 11.5px; color: #5F5E5A;
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 999px; padding: 3px 11px; margin: 2px 6px 2px 0;
}
.nx-refnote { font-size: 12px; color: var(--c-caption); margin: 6px 0 2px; }
.nx-meta { font-size: 11.5px; color: var(--c-caption); margin-top: 8px; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)
st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)
st.markdown('<span class="nx-beta">베타 · 입력 내용은 학습에 사용되지 않습니다</span>',
            unsafe_allow_html=True)

_EXAMPLES = (
    "법인카드 사용 기준이 어떻게 되나요?",
    "협력사에서 선물을 받았는데 어떻게 해야 하나요?",
    "국내 출장 시 숙박비 한도가 궁금합니다.",
    "외부에서 강연 요청이 왔는데 회사 승인이 필요한가요?",
    "매장에서 손님이 두고 간 물건은 어떻게 처리하나요?",
    "거래처가 명절 선물을 보내왔어요. 받아도 되나요?",
)

# 질의 범위 (표시 계층 — 선택 시 질문에 범위 문구를 부가해 라우터·합성이 참고)
_SCOPES = ("전체", "CSR", "공정거래", "공통", "안전", "영업", "인사",
           "재무", "정보보안", "총무", "환경")

# conf 4등급 → 사용자 라벨 (심의 결정 3항 — UI 표기 의무. 산식 무접촉)
_GRADE_LABEL = {
    "HIGH": ("high", "✓ 사규 원문 근거 확인"),
    "MEDIUM": ("medium", "참고 문서 기반 — 원문 대조 권장"),
    "UNVERIFIED": ("unv", "조항 단위 근거 미확인 — 원문 확인 권장"),
    # LOW 는 기존 강등 칩(안전 표면)이 담당 — 중복 표기 안 함
}

_STANCE_TONE = {   # v1 판정 카드 색조 이식 (안전쪽 = 레드)
    "금지":   ("#C8102E", "#FCEEF0"),
    "신고대상": ("#C8102E", "#FCEEF0"),
    "조건부":  ("#B7791F", "#FBF3E2"),
    "허용":   ("#2F7A4D", "#EAF5EE"),
    "확인필요": ("#6B6A66", "#F0EFEC"),
}


def _verdict_card_data(answer: str, citations: list) -> dict | None:
    """판정 카드 데이터 — 결정론 텍스트 파싱 (표시 계층 전용, LLM·엔진 무접촉).

    stance: 핵심 결론 문구의 키워드 → v1 색조 체계. 대표 인용은 📋 사규 기준
    첫 문장, 출처는 verify ok 쌍 우선. 파싱 실패 시 None → 카드 생략(안전).
    """
    import re as _re
    m = _re.search(r"\*\*핵심 결론\*\*\s*\n(.+?)(?:\n\s*\n|\n\*\*)", answer, _re.DOTALL)
    if not m:
        return None
    concl = m.group(1).strip().replace("\n", " ")
    if any(k in concl for k in ("불가", "금지", "안 됩니다", "안됩니다", "위반")):
        stance = "금지"
    elif any(k in concl for k in ("신고", "보고해야")):
        stance = "신고대상"
    elif any(k in concl for k in ("조건", "제한", "한하여", "경우에만", "승인", "사전")):
        stance = "조건부"
    elif any(k in concl for k in ("가능", "허용", "무방")):
        stance = "허용"
    else:
        stance = "확인필요"
    label = concl[:60] + ("…" if len(concl) > 60 else "")
    q = _re.search(r"\*\*📋 사규 기준\*\*\s*\n[\-\*\s]*(.+?)(?:\n|$)", answer)
    quote = (q.group(1).strip()[:120] if q else "")
    cite = ""
    for c in citations or []:
        if c.get("verdict") == "ok" and c.get("document_title"):
            cite = c["document_title"] + (f" {c['article_no']}" if c.get("article_no") else "")
            break
    return {"stance": stance, "label": label, "quote": quote, "cite": cite}

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
        st.markdown('<p class="nx-brand-eyebrow">질의 범위</p>',
                    unsafe_allow_html=True)
        st.selectbox("질의 범위", _SCOPES, index=0, key="scope",
                     label_visibility="collapsed")
        st.caption("범위를 고르면 질문에 해당 분야 표시가 함께 전달됩니다.")
        st.markdown("---")
        st.markdown(
            '<p class="nx-disclaimer">'
            "본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다.<br>"
            "신고·조사 사항은 CSR팀 또는 신세계면세점 핫라인으로,<br>"
            "인사 규정·복리후생 등 인사 행정 사항은 인사교육팀으로 "
            "문의해 주시기 바랍니다.</p>",
            unsafe_allow_html=True)


def _render_assistant(entry: dict, idx: int = 0) -> None:
    """안전 표면 단일 렌더 경로 — 불변 조건 3종은 전부 이 함수 안에 있다.

    ① blocked → 답변 미표출 + 차단 안내 (verify block)
    ② critical → 배너 + (enforce_structure 된) 답변
    ③ degrade → ⚠ 신뢰도 강등 칩 + 답변
    UI 패리티(08-06 안건) 추가 표면: 판정 카드·grade 라벨·참고 인용 구획·
    출처 칩·검토 과정·응답 시간·피드백·후속 제안 — 전부 표시 계층.
    """
    import html as _h
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
    # grade 라벨 (심의 3항 UI 표기 — LOW 는 위 강등 칩이 담당, 중복 없음)
    g = entry.get("grade")
    if g in _GRADE_LABEL and not entry.get("critical"):
        cls, label = _GRADE_LABEL[g]
        st.markdown(f'<span class="nx-grade {cls}">{label}</span>',
                    unsafe_allow_html=True)
    # 판정 카드 (v1 verdict 표면 이식 — 결정론 파싱, critical 제외)
    card = entry.get("card")
    if card:
        color, bg = _STANCE_TONE.get(card["stance"], ("#6B6A66", "#F0EFEC"))
        html = (f'<div class="nx-vd" style="--vd-c:{color};--vd-bg:{bg}">'
                f'<span class="nx-vd-pill"><span class="ico"></span>'
                f'<b>{_h.escape(card["label"])}</b></span>')
        if card.get("quote"):
            html += (f'<div class="nx-vd-quote"><p>{_h.escape(card["quote"])}'
                     "</p></div>")
        if card.get("cite"):
            html += f'<span class="nx-vd-cite">📕 {_h.escape(card["cite"])}</span>'
        st.markdown(html + "</div>", unsafe_allow_html=True)
    # '참고 인용' 구획 캡션 — 무응답 표명 + 인용 존재 시 (표시만, 판정식 무접촉)
    _neg_markers = ("확인되지 않", "확인할 수 없", "사규에서 확인되지 않")
    if (any(m in (entry.get("answer") or "") for m in _neg_markers)
            and entry.get("cite_n", 0) > 0 and not entry.get("critical")):
        st.markdown('<p class="nx-refnote">※ 아래 인용은 질문에 대한 직접 '
                    "근거가 아닌 <b>참고 규정</b>입니다.</p>",
                    unsafe_allow_html=True)
    st.markdown(entry["answer"])
    # 출처 문서 칩
    if entry.get("ctx_titles") and not entry.get("blocked"):
        chips = "".join(f'<span class="nx-doc-chip">📄 {_h.escape(t)}</span>'
                        for t in entry["ctx_titles"])
        st.markdown(chips, unsafe_allow_html=True)
    # 🧠 검토 과정 (접힘) — 사용자 친화 문구
    if entry.get("n_chunks") is not None:
        with st.expander("🧠 AI 검토 과정", expanded=False):
            t = entry.get("timings") or {}
            steps = [f"사규 검색 — 관련 발췌 {entry.get('n_chunks')}건 확보"
                     + (f" ({(t.get('rpc_ms', 0) + t.get('embed_ms', 0)) / 1000:.1f}초)"
                        if t.get("rpc_ms") else "")]
            if entry.get("router_hit"):
                steps.append("지배 규정 라우팅 — 핵심 문서를 우선 확보")
            if t.get("rerank_ms"):
                steps.append(f"관련도 재정렬 ({t['rerank_ms'] / 1000:.1f}초)")
            steps.append(f"답변 작성" + (f" — 재작성 {entry['retries']}회 수행"
                                     if entry.get("retries") else ""))
            steps.append(f"인용 검증 — {entry.get('cite_ok', 0)}건 원장 대조 통과"
                         f" / 인용 {entry.get('cite_n', 0)}건")
            for s_ in steps:
                st.markdown(f"- {s_}")
    # 응답 시간·피드백
    if entry.get("elapsed_s"):
        st.markdown(f'<p class="nx-meta">⏱️ 응답 {entry["elapsed_s"]}초</p>',
                    unsafe_allow_html=True)
    if not entry.get("blocked"):
        fb_key = f"fb_{idx}"
        if st.session_state.get(fb_key):
            st.caption("피드백이 기록되었습니다. 감사합니다.")
        else:
            c1, c2, _sp = st.columns([1, 1, 6])
            if c1.button("👍 도움됨", key=f"{fb_key}_up"):
                st.session_state[fb_key] = "up"
                print(f"[ui:feedback] idx={idx} v=up", file=sys.stderr, flush=True)
                st.rerun()
            if c2.button("👎 아쉬움", key=f"{fb_key}_dn"):
                st.session_state[fb_key] = "down"
                print(f"[ui:feedback] idx={idx} v=down", file=sys.stderr, flush=True)
                st.rerun()
    # 후속 질문 제안 (grounded — DB 실재 예시만)
    if entry.get("followups"):
        st.caption("이어서 물어보기")
        cols = st.columns(len(entry["followups"]))
        for j, (col, fq) in enumerate(zip(cols, entry["followups"])):
            if col.button(fq, key=f"fu_{idx}_{j}", use_container_width=True):
                st.session_state["pending_q"] = fq
                st.rerun()


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
    verdict = verify_answer(syn.answer_md, ledger,
                            synthesis_integrity_ok=syn.integrity_ok)

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
    # 후속 질문 제안 — 최종 컨텍스트 문서의 auto_query_examples SELECT (읽기
    # 전용, grounded — 실재 예시만. v1 grounded_suggestions 의 표시 계층 이식)
    followups: list[str] = []
    if not blocked and not intake["is_critical"]:
        try:
            doc_ids = list({c["document_id"] for c in res["chunks"]})[:5]
            rows = (sb.table("nexus_documents")
                    .select("auto_query_examples").in_("id", doc_ids)
                    .execute().data or [])
            seen: set[str] = set()
            for r in rows:
                for ex in (r.get("auto_query_examples") or []):
                    ex = str(ex).strip()
                    if ex and ex != question and ex not in seen:
                        seen.add(ex)
                        followups.append(ex)
            followups = followups[:3]
        except Exception:
            followups = []
    ctx_titles = sorted({c["breadcrumb"].split(">")[0] for c in res["chunks"]
                         if c.get("breadcrumb")})
    card = None
    if not blocked and not intake["is_critical"]:
        card = _verdict_card_data(syn.answer_md, verdict["citations"])
    return {
        "role": "assistant",
        "answer": "" if blocked else answer,   # block 답변은 저장조차 안 함
        "blocked": blocked,
        "critical": bool(intake["is_critical"]),
        "degraded": verdict["action"] == "degrade",
        # ── UI 패리티 (표시 전용 필드) ──
        "grade": verdict["grade"],
        "card": card,
        "ctx_titles": ctx_titles,
        "cite_ok": sum(1 for c in verdict["citations"] if c["verdict"] == "ok"),
        "cite_n": len(verdict["citations"]),
        "followups": followups,
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "provider": syn.provider,
        "timings": res.get("timings", {}),
        "router_hit": res.get("router_hit"),
        "n_chunks": len(res["chunks"]),
        "retries": syn.retries,
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
        '<p class="nx-hero-eyebrow">사규의 나침반 · Compliance Compass</p>'
        '<p class="nx-hero-title">무엇을 확인해 드릴까요?</p>'
        '<p class="nx-hero-sub">신세계디에프 사규를 근거와 함께 안내합니다. '
        "상황을 그대로 적어 주셔도 됩니다 — 아래 예시를 눌러도 좋습니다."
        "</p></div>",
        unsafe_allow_html=True)
    for row_start in (0, 3):
        cols = st.columns(3)
        for i, (col, ex) in enumerate(
                zip(cols, _EXAMPLES[row_start:row_start + 3]), start=row_start):
            if col.button(ex, key=f"ex_{i}", use_container_width=True):
                st.session_state["pending_q"] = ex
                st.rerun()

for i, m in enumerate(st.session_state["messages"]):
    if m["role"] == "user":
        with st.chat_message("user"):
            st.markdown(m["content"])
    else:
        with st.chat_message("assistant", avatar="🧭"):
            _render_assistant(m, idx=i)

if question:
    # 질의 범위 (표시 계층 조립 — 선택 시 범위 문구 부가, 엔진 코드 무접촉)
    scope = st.session_state.get("scope", "전체")
    engine_q = question if scope in (None, "전체") \
        else f"{question} (질의 범위: {scope})"
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🧭"):
        with st.spinner("사규를 확인하고 답변을 작성하는 중…"):
            entry = _ask(engine_q)
        _render_assistant(entry, idx=len(st.session_state["messages"]))
    st.session_state["messages"].append(entry)
