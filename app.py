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
p.nx-hero-title, .nx-hero-title {
  font-size: 54px !important; font-weight: 800 !important; color: #1A1A1A !important;
  letter-spacing: -0.03em !important; line-height: 1.12 !important;
  margin: 0 0 16px !important;
}
.nx-hero-title .q { color: var(--c-accent) !important; }
p.nx-hero-eyebrow { font-size: 12px !important; }
p.nx-hero-sub { font-size: 15px !important; }
.nx-hero-sub { font-size: 15px; color: #767676; line-height: 1.7; margin: 0; font-weight: 400; }
/* 랜딩 상단 로고 라인 + 우측 베타 칩 (v1 topbar2 정합) */
.nx-top2 { display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0 6px; }
.nx-top2 .brand { display: flex; align-items: baseline; gap: 10px; }
.nx-top2 .name { font-size: 17px; font-weight: 800; color: #1A1A1A; letter-spacing: -0.01em; }
.nx-top2 .tag { font-size: 12px; color: var(--c-caption); }
/* 전폭 베타 배너 (v1 정합 — 방패 + 사이드바 안내) */
.nx-beta-bar { display: flex; align-items: center; gap: 10px;
  background: #F0EFEA; border: 1px solid var(--c-border); border-radius: 8px;
  padding: 9px 14px; font-size: 12.5px; color: #6B6A66; margin: 6px 0 4px; }
/* 히어로 중앙 대형 입력 + 원형 레드 전송 (st-key 스코프) */
[class*="st-key-hero_q"] input {
  height: 60px !important; font-size: 16px !important;
  border-radius: 999px !important; border: 1.5px solid var(--c-border) !important;
  background: #fff !important; padding: 0 26px !important;
  box-shadow: 0 2px 10px rgba(31,30,29,0.06) !important;
}
[class*="st-key-hero_q"] input:focus { border-color: var(--c-accent) !important; }
[class*="st-key-hero_go"] .stButton > button,
[class*="st-key-hero_go"] button {
  width: 60px !important; height: 60px !important; min-height: 60px !important;
  border-radius: 50% !important; background: var(--c-accent) !important;
  border: 1px solid var(--c-accent) !important; color: #fff !important;
  font-size: 20px !important; padding: 0 !important; text-align: center !important;
}
[class*="st-key-hero_go"] .stButton > button p { color: #fff !important; }
[class*="st-key-hero_go"] .stButton > button:hover,
[class*="st-key-hero_go"] button:hover { background: var(--c-accent-dark) !important; }
/* 히어로 예시 칩 — pill 형 (v1 정합) */
[class*="st-key-ex_"] .stButton > button,
[class*="st-key-ex_"] button {
  border-radius: 999px !important; background: #fff !important;
  border: 1px solid var(--c-border) !important; text-align: center !important;
  font-size: 12.5px !important; padding: 0.55rem 1rem !important;
}
[class*="st-key-ex_"] .stButton > button:hover,
[class*="st-key-ex_"] button:hover { border-color: var(--c-accent) !important;
  color: var(--c-accent) !important; }

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

/* ── 시간축(모션) F 계급 — v1 ui/styles.py:750-784 keyframes +
      app.py:734-746 THINKING 블록 이식 ── */
@keyframes nx-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
@keyframes nx-pulse {
  0%, 100% { opacity: 1;    transform: scale(1);    }
  50%      { opacity: 0.55; transform: scale(1.18); }
}
@keyframes nx-cycle {
  0%, 24%   { content: "🧠"; }
  25%, 49%  { content: "💭"; }
  50%, 74%  { content: "✍️"; }
  75%, 100% { content: "📝"; }
}
.nx-pulse { animation: nx-pulse 1.4s ease-in-out infinite; display: inline-block; }
.nx-cycle::before { content: "🧠"; animation: nx-cycle 2s linear infinite;
  display: inline-block; }
.nx-think { display: flex; align-items: center; gap: 14px; padding: 16px 4px; }
.nx-think-spin { display: inline-flex; align-items: center; justify-content: center;
  width: 44px; height: 44px; border-radius: 50%; background: rgba(200,16,46,0.08);
  font-size: 22px; animation: nx-spin 2s linear infinite; }
.nx-think-txt { display: flex; flex-direction: column; gap: 3px; }
.nx-think-line { font-size: 15px; font-weight: 600; color: var(--c-primary); }
.nx-think-sub { font-size: 12.5px; color: #9A968D; }
/* PROACTIVE DOCK 주 액션 + 동의 제출 — 레드 primary (v1 type="primary" 정합) */
[class*="st-key-dock_"] .stButton > button,
[class*="st-key-consent_submit"] .stButton > button {
  background: var(--c-accent) !important; border-color: var(--c-accent) !important;
  color: #fff !important; text-align: center !important; font-weight: 700 !important;
}
[class*="st-key-dock_"] .stButton > button p,
[class*="st-key-consent_submit"] .stButton > button p { color: #fff !important; }
[class*="st-key-dock_"] .stButton > button:hover,
[class*="st-key-consent_submit"] .stButton > button:hover {
  background: var(--c-accent-dark) !important; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)
st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)
st.markdown(
    '<div class="nx-top2"><span class="brand">🧭 '
    '<span class="name">DF COMPASS</span>'
    '<span class="tag">사규의 나침반</span></span>'
    '<span class="nx-beta">베타 · 입력 내용 학습 안 함</span></div>',
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

# personality (v1 core/personality.py:31-99 이식 — 표시 계층 결정론+random)
_CLOSING_NORMAL = (
    "오늘도 좋은 하루 되세요. 추가 질문 환영입니다.",
    "도움이 되었길 바랍니다. 더 궁금한 점은 언제든 물어보세요.",
    "사규 관련 질문은 언제든 환영입니다.",
)
_CLOSING_CRITICAL = (
    "혼자 감당하지 마세요. CSR팀에 언제든 연락 주세요.",
    "도움이 필요하시면 핫라인에 문의 바랍니다.",
    "회사는 늘 곁에 있습니다. 필요할 때 핫라인을 이용해 주세요.",
)
_GREET = {
    "weekend": "주말에도 수고 많으십니다. 무엇을 도와드릴까요?",
    "friday_pm": "주말 앞두고 잘 정리하세요. 사규 관련 질문은 언제든 환영입니다.",
    "monday_am": "한 주의 시작, 컴플라이언스 질문 편하게 주세요.",
    "morning": "좋은 아침입니다. 무엇을 확인해 드릴까요?",
    "noon": "점심 전후로도 사규 질문 환영입니다.",
    "afternoon": "오후에도 수고 많으십니다. 무엇을 도와드릴까요?",
    "evening": "저녁에도 수고 많으십니다. 사규 질문 편하게 주세요.",
    "night": "야간에도 수고 많으십니다. 사규 관련 질문은 언제든 환영입니다.",
}


def _greeting_line() -> str:
    """v1 fallback_greeting 버킷 로직 이식 (personality.py:96-121, KST)."""
    from datetime import datetime, timedelta, timezone
    n = datetime.now(timezone(timedelta(hours=9)))
    wd, hr = n.weekday(), n.hour
    if wd >= 5:
        b = "weekend"
    elif wd == 4 and hr >= 14:
        b = "friday_pm"
    elif wd == 0 and hr < 12:
        b = "monday_am"
    elif 5 <= hr < 12:
        b = "morning"
    elif 12 <= hr < 14:
        b = "noon"
    elif 14 <= hr < 18:
        b = "afternoon"
    elif 18 <= hr < 22:
        b = "evening"
    else:
        b = "night"
    return _GREET[b]


def _closing_line(is_critical: bool, idx: int) -> str:
    """v1 closing_remark 이식 (personality.py:46-50) — 세션 결정론 pick."""
    pool = _CLOSING_CRITICAL if is_critical else _CLOSING_NORMAL
    return pool[idx % len(pool)]


# 카테고리 뱃지 (v1 ui/render.py:142-165 — 접두어 최빈값 결정론)
_CAT_ICON = {"재무": "💳", "안전": "🦺", "인사": "👥", "공정거래": "⚖️",
             "CSR": "🤝", "영업": "🏬", "총무": "🏢", "정보보안": "🔐",
             "환경": "🌿", "공통": "📌"}


def _category_of(ctx_titles: list) -> str | None:
    import re as _re
    from collections import Counter as _C
    cats = [m.group(1) for t in (ctx_titles or [])
            if (m := _re.match(r"\((.+?)\)", t))]
    return _C(cats).most_common(1)[0][0] if cats else None


def _has_citation_form(answer: str) -> bool:
    """섹션/문서 인용 표기 존재 (결함1 라벨 분기용 — 표시 계층 결정론).
    [참조: …] 블록 · 「문서명」 · 계약형 ((카테고리) 문서명, "섹션") 3형."""
    import re as _re
    return bool(_re.search(
        r"\[참조:|「[^」]{2,}」|\(\([^()]{1,20}\)\s*[^,()]{2,},\s*\"", answer))


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
    concl = m.group(1).strip().replace("\n", " ").replace("**", "")
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
    quote = (q.group(1).strip().replace("**", "")[:120] if q else "")
    cite = ""
    for c in citations or []:
        if c.get("verdict") == "ok" and c.get("document_title"):
            cite = c["document_title"] + (f" {c['article_no']}" if c.get("article_no") else "")
            break
    return {"stance": stance, "label": label, "quote": quote, "cite": cite}

_BLOCK_MESSAGE = ("이 답변은 비실재 문서 인용이 감지되어 차단되었습니다. "
                  "질문을 바꿔 다시 시도하거나 담당 부서에 문의해 주세요.")

# 피드백 사유 풀 (v1 ui/feedback.py:12-25 원문)
_FB_REASONS_NEG = ["사실과 달라요", "출처가 부족해요", "질문 의도 못 파악",
                   "답변이 모호함", "신고·문의 안내 누락", "기타"]
_FB_REASONS_POS = ["정확해요", "출처가 명확", "실무에 바로 적용 가능", "기타"]

# ── 베타 참가 동의서 (v1 app.py:1318-1358 원문 기반 — 데이터 흐름 서술만
#    v2 실태로 정정: v2 는 질의 로그·동의 기록을 DB 에 저장하지 않는다(ADR-8).
#    영속 기록은 ADR-8 심의 후 도입) ──
_CONSENT_BODY_MD = """
**본 챗봇은 베타 테스트 중이며, 정보처리자가 회사가 아닌 개별 운영자입니다.**
정식 OPEN 시 회사 GCP(Vertex AI) + 회사 Supabase 로 이관 예정이며,
그 시점부터 회사가 정보처리자가 됩니다.

참가자께서는 아래 내용을 확인·동의하신 뒤 베타 테스트에 참여해 주시기 바랍니다.

1. **데이터 흐름**
   - 입력하신 질의는 `[익명]` 마스킹 후 외부 LLM API로 전송되어 답변이 생성됩니다.
   - 사용 LLM (베타 단계):
     - 주(主) 모델: Google Gemini API (유료 티어)
     - 보조 모델: Anthropic Claude API (Gemini API 일시 장애 시 자동 우회)
   - **두 API 모두 약관상 입력·출력이 모델 학습에 사용되지 않습니다.**
     - Gemini 유료 티어: Google API 약관에 따라 학습 제외
     - Claude API: Anthropic Commercial Terms 에 따라 학습 제외
   - 다만 양사는 **이용약관 위반 모니터링(Trust & Safety) 목적**으로 입력·
     출력을 단기간 보관할 수 있습니다 (Anthropic 기본 최대 30일, Google
     정책 동일 수준). **이 보관은 모델 학습과 무관**하며 보관 기간 종료
     시 자동 폐기됩니다.
   - 본 베타(v2) 단계에서는 **질의 로그를 데이터베이스에 저장하지 않습니다.**
     원본 질의는 답변 생성 후 즉시 폐기됩니다.

2. **인프라 주체 (베타 한정)**
   - Supabase 프로젝트 / Gemini · Claude API 키 모두 **개별 운영자(개인)** 명의입니다.
   - 회사-Google 간 DPA(데이터 처리 계약) 및 회사 차원의 처리방침 고지는
     **정식 OPEN 후** 적용됩니다.

3. **답변 한계**
   - 본 챗봇은 사규 해석 보조 도구이며 **법적 효력이 없습니다.**
   - 신고·조사 사항은 CSR팀 또는 신세계면세점 핫라인으로 접수해 주시기 바랍니다.
   - 인사 규정·복리후생 등 인사 행정 사항은 인사교육팀에 문의해 주시기 바랍니다.

4. **수집 정보**
   - 본 동의 화면에서 입력하신 **성명·사번**은 동의 확인 목적으로 운영
     로그에만 남으며, 데이터베이스에 저장되지 않습니다.

5. **철회**
   - 동의 후에도 운영자(`ADMIN`)에게 요청하시면 관련 기록을 삭제할 수 있습니다.
"""


def _consent_gate() -> bool:
    """베타 참가 동의 게이트 (v1 app.py:1411-1533 표시 계층 이식).

    운영(`NEXUS_ENV=prod*`)에서는 비활성. v1 과 달리 쿠키 영속·DB 기록 없음
    (ADR-8: DB 쓰기 금지 — 세션 통과 + stderr 기록. v1 의 CookieManager 는
    rerun 인터럽트 사고 이력이 있어 의존성째 미이식)."""
    env = os.environ.get("NEXUS_ENV", "beta-personal")
    if env.startswith("prod"):
        return True
    ver = os.environ.get("NEXUS_CONSENT_VERSION", "v1")
    if st.session_state.get("beta_consent_v") == ver:
        return True
    st.markdown(
        '<div class="nx-hero" style="margin-bottom:24px">'
        '<p class="nx-hero-eyebrow">BETA · 사전 동의</p>'
        '<p class="nx-hero-title">베타 참가 동의서</p>'
        '<p class="nx-hero-sub">본 환경은 정식 OPEN 전 베타 테스트입니다. '
        "아래 내용을 확인하시고 동의해 주신 분께만 베타 챗봇이 활성화됩니다."
        "</p></div>",
        unsafe_allow_html=True)
    st.markdown(_CONSENT_BODY_MD)
    st.markdown("---")
    c1, c2 = st.columns(2)
    name = c1.text_input("성명 *", value="", key="consent_name")
    emp_no = c2.text_input("사번 (선택)", value="", key="consent_emp")
    agree = st.checkbox("위 내용을 모두 읽고 베타 참가에 동의합니다.",
                        key="consent_agree")
    if st.button("동의하고 시작", key="consent_submit"):
        # 입력 검증 (v1 app.py:1497-1509 원문 — stored XSS/SQL 페이로드 차단)
        import re as _re
        if not name.strip():
            st.error("성명을 입력해 주세요.")
        elif not _re.match(r"^[가-힣A-Za-z\s]{1,50}$", name.strip()):
            st.error("성명은 한글·영문·공백만 사용해 주세요 (1~50자).")
        elif emp_no.strip() and not _re.match(r"^[0-9-]{4,12}$", emp_no.strip()):
            st.error("사번은 숫자 4~12자 (하이픈 허용) 형식이어야 합니다.")
        elif not agree:
            st.error("동의 체크박스를 선택해 주세요.")
        else:
            print(f"[ui:consent] v={ver} name={name.strip()} "
                  f"emp={emp_no.strip() or '-'}", file=sys.stderr, flush=True)
            st.session_state["beta_consent_v"] = ver
            st.rerun()
    return False


def _check_rate_limit() -> bool:
    """세션 단위 일일 질의 한도 — 베타 비용 가드 (v1 app.py:515-532 이식).
    KST 자정 기준 리셋. 통과 시 카운터 증가 + True."""
    import datetime as _dt
    limit = int(os.environ.get("NEXUS_DAILY_QUERY_LIMIT", "100"))
    kst = _dt.timezone(_dt.timedelta(hours=9))
    today = _dt.datetime.now(kst).date().isoformat()
    rec = st.session_state.get("_rate_rec") or {"date": today, "count": 0}
    if rec["date"] != today:
        rec = {"date": today, "count": 0}
    if rec["count"] >= limit:
        st.session_state["_rate_rec"] = rec
        return False
    rec["count"] += 1
    st.session_state["_rate_rec"] = rec
    return True


# ── 이해 확인 + 구체화 유도 표면 (08-06 사용자 설계 — 표시 계층 전용) ──
# 파편·지시어 후속 질문을 엔진 호출 _전_ 에 감지해, 검색을 돌리지 않고
# 단일 턴 안내 + 직전 답변 기반 구체화 칩(실재 예시만)을 보여준다.
# 감지 실패 = 현행 동작 그대로 (no-op 폴백). 엔진(검색·합성·verify) 무접촉.
_FRAG_STARTS = ("그럼", "그거", "그건", "그게", "그러면", "그래서", "근데",
                "그리고", "아까", "방금", "위에", "그때", "그럴", "그거는")
_FRAG_BARE = ("얼마", "언제", "왜", "어디", "누가", "누구", "어떻게", "몇",
              "한도는", "기준은", "되는데", "안되", "안 되")


def _is_fragment_followup(q: str, has_prev: bool) -> bool:
    """지시어로 시작하거나 짧은 파편형 질문 + 직전 턴 존재 → True.
    자기완결형(길거나 목적어가 앞에 오는) 질문은 가로채지 않는다 (보수적)."""
    if not has_prev:
        return False
    t = (q or "").strip()
    if not t or len(t) > 25:
        return False
    if any(t.startswith(s) for s in _FRAG_STARTS):
        return True
    return len(t) <= 12 and any(t.startswith(s) for s in _FRAG_BARE)


# ── PROACTIVE DOCK "다음 단계 예측" (v1 ui/feedback.py:112-140 이식) ──
# 08-07 결함4 재설계: 분기 = 답변 내 명시적 신고 신호 + 카테고리(뱃지와 동일
# 산출) 결정론 매핑만. v1 classify_button 의 confidence="low" fallback 을
# grade UNVERIFIED 로 대응시킨 것이 오분기 원인이었다 — v1 에선 low 가
# 희귀하지만 v2 는 C-class 문서(76/101)가 전부 UNVERIFIED 라 hr fallback 이
# 광역 오발동. 질문 키워드 휴리스틱도 제거 — 확신 없으면 생략(오안내<무안내).
_A_BROAD_KW = ("신고·조사", "SRMS", "신세계면세점 핫라인", "일반 사건사고 보고지침",
               "중대 사건사고 보고지침", "사건사고 보고지침", "공정거래법 위반",
               "공정거래를 저해", "위변조 또는 허위작성", "부정/부실행위")
_A_CLEAN_KW = ("클린신고", "클린뱅크", "자진 신고", "자진신고", "클린신고서",
               "클린신고신청서", "SHRS CSR경영란", "CSR경영란", "윤리실천등록")
_A_HR_KW = ("인사 규정·복리후생 등 인사 행정 사항은 인사교육팀에 문의",
            "인사교육팀에 문의해 주시기 바랍니다",
            "인사 규정·복리후생 등 인사 행정 사항은 인사팀에 문의",
            "인사팀에 문의해 주시기 바랍니다")
_CAT_DOCK = {"재무": "finance", "인사": "hr", "CSR": "clean"}


def _dock_branch(entry: dict) -> str:
    if entry.get("critical"):
        return "report"
    ans = entry.get("answer") or ""
    a_clean = any(k in ans for k in _A_CLEAN_KW)
    a_broad = any(k in ans for k in _A_BROAD_KW)
    if a_clean and not a_broad:
        return "clean"
    if a_broad:
        return "report"
    if any(k in ans for k in _A_HR_KW):
        return "hr"
    cat = _category_of(entry.get("ctx_titles") or [])
    return _CAT_DOCK.get(cat or "", "hidden")


def _render_dock_panel(branch: str, hotlines: dict) -> None:
    """신고/클린신고/인사 문의 패널 (v1 ui/panels.py 3종 축약 이식)."""
    ethics = (hotlines.get("ethics_hotline_url") or "").strip()
    anon = (hotlines.get("internal_report_url") or "").strip()
    ext = (hotlines.get("external_hotline") or "").strip()
    with st.container(border=True):
        if branch == "report":
            st.markdown("**📞 신고 방법 안내**")
            st.markdown("신고·조사 사항은 **CSR팀** 또는 **신세계면세점 "
                        "핫라인**으로 접수해 주시기 바랍니다.")
            st.markdown("**📋 1차 보고**: SRMS 시스템 즉시 등록 (인지 시점 24시간 內)")
            st.link_button("🔗 SRMS 바로가기", "https://rms.shinsegae.com/",
                           use_container_width=True)
            if ethics:
                st.link_button("🏢 신세계면세점 핫라인", ethics,
                               use_container_width=True)
        elif branch == "finance":
            # 결함4 (08-07): 재무 카테고리 결정론 매핑 — 본문 권장 행동과
            # 동일한 담당 부서 안내 (경리팀 카드 관리 · 경영관리팀 예산 합의)
            st.markdown("**💳 재무 담당 부서 안내**")
            st.markdown("법인카드·경비 등 재무 실무는 **경리팀**(카드 관리), "
                        "예산 협의는 **경영관리팀**(예산 합의)에 문의해 "
                        "주시기 바랍니다.")
        elif branch == "clean":
            st.markdown("**💼 클린신고 (자진 신고) 안내**")
            st.markdown("금품·향응 수수 등 이해관계자와의 비위 행위는 "
                        "**SHRS**의 **클린신고신청서**를 통해 자진 신고하시기 바랍니다.")
            st.markdown("**📋 등록방법**:  \nSHRS → **윤리경영** → "
                        "**윤리실천등록** → **클린신고신청서**")
            st.markdown("**📋 신고 기한**: 수수 확인일로부터 **3일 이내** "
                        "(7일 이내 자진 신고 시 징계 감경 가능)")
            st.link_button("🔗 SHRS 바로가기", "https://hr.shinsegae.com/index.jsp",
                           use_container_width=True)
        else:   # hr
            st.markdown("**📞 인사교육팀 문의 채널**")
            st.markdown((hotlines.get("hr_contact_text") or "").strip()
                        or "인사교육팀에 직접 문의하세요.")
            hr_bot = (hotlines.get("hr_chatbot_url") or "").strip()
            if hr_bot:
                st.link_button("💬 사내 인사 챗봇", hr_bot, use_container_width=True)
        if anon:
            st.link_button("🔒 사내 익명 제보 채널", anon, use_container_width=True)
        if ext:
            st.markdown(f"📞 외부 상담채널: {ext}")
        st.caption("⚠️ 본 답변은 사규 해석 보조이며, 실제 신고·문의는 사규 "
                   "절차에 따라 직접 진행하시기 바랍니다.")


_DOCK_LABEL = {"hr": "📞 인사교육팀 문의", "clean": "💼 클린신고 안내",
               "report": "📞 신고 방법 안내",
               "finance": "💳 경리팀·경영관리팀 안내"}


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


# ── 시간축(모션) 대기 표면 — F 계급 (v1 app.py:702-820 이식) ──
_TIMER_HTML = """
<div style="background:#FAF6F1;padding:10px 14px;border-radius:10px;
     font-family:-apple-system,'Segoe UI',sans-serif;font-size:13px;color:#666;
     display:flex;justify-content:space-between;align-items:center;
     border:1px solid #EDE6DC;box-sizing:border-box;">
  <span>⏱️ <span id="dfc-elapsed" style="font-weight:600;color:#C8102E;">0</span>초 경과</span>
  <span style="font-size:12px;color:#9A968D;">예상 소요 약 20~60초</span>
</div>
<script>
  (function() {
    var start = Date.now();
    var elem = document.getElementById('dfc-elapsed');
    if (!elem) return;
    setInterval(function() {
      elem.innerText = Math.round((Date.now() - start) / 1000);
    }, 250);
  })();
</script>
"""


def _nx_iframe(html: str, *, height: int = 0) -> None:
    """v1 app.py:9-21 이식 — st.iframe 우선, 구 components.html 폴백.
    iframe 내부 JS 가 self-contained 로 동작 (실시간 경과 카운터)."""
    fn = getattr(st, "iframe", None)
    if fn is not None and height > 0:
        fn(html, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=height)


def _request_stop() -> None:
    """⏹ 생성 중지 on_click (v1 app.py:555-557) — 클릭이 rerun 을 유발해
    진행 중 런이 중단·결과 폐기되고, 다음 런 상단이 플래그를 안내로 전환."""
    st.session_state["_stop_requested"] = True


def _spinner_html(line: str, sub: str = "", cycle: bool = False) -> str:
    """v1 app.py:756-763 THINKING 스피너 — cycle=True 는 답변 작성 단계의
    이모지 순환(nx-cycle, v1 PR-Fun1.9)."""
    icon = ('<span class="nx-think-spin" style="animation:none">'
            '<span class="nx-cycle"></span></span>' if cycle
            else '<span class="nx-think-spin">🧭</span>')
    s = f'<div class="nx-think-sub">{sub}</div>' if sub else ""
    return (f'<div class="nx-think">{icon}<div class="nx-think-txt">'
            f'<div class="nx-think-line">{line}</div>{s}</div></div>')


def _typewriter(text: str):
    """검증 완료 텍스트의 타이핑 재생 제너레이터 (표시 계층 전용).

    ⚠️ 실제 토큰 스트리밍 아님 — v2 안전 체계(절단 게이트·verify·판정 카드)는
    "완성 → 검증 → 표시" 순서가 전제라, 이미 통과된 최종 텍스트만 재생한다
    (실 스트리밍 전환은 설계 변경 — 별도 심의 대상, 08-06 사용자 확정).
    """
    step = 6                                   # 문자 단위 청크 — 자연스러운 속도
    for i in range(0, len(text), step):
        yield text[i:i + step]
        time.sleep(0.012)


def _render_assistant(entry: dict, idx: int = 0, typing: bool = False) -> None:
    """안전 표면 단일 렌더 경로 — 불변 조건 3종은 전부 이 함수 안에 있다.

    ① blocked → 답변 미표출 + 차단 안내 (verify block)
    ② critical → 배너 + (enforce_structure 된) 답변
    ③ degrade → ⚠ 신뢰도 강등 칩 + 답변
    UI 패리티(08-06 안건) 추가 표면: 판정 카드·grade 라벨·참고 인용 구획·
    출처 칩·검토 과정·응답 시간·피드백·후속 제안 — 전부 표시 계층.
    typing=True (신규 답변 1회): 안전 표면·카드·라벨은 **즉시** 표시하고
    본문만 타이핑 재생 — 히스토리 리플레이는 정적 표시.
    """
    import html as _h
    # 비용 가드 안내 (엔진 미호출 턴 — 히스토리 영속 표시)
    if entry.get("notice"):
        st.warning(entry["notice"])
        return
    # 오류 안내 — 처리 후 rerun(v1 :1913) 에서도 살아남도록 영속 엔트리
    if entry.get("notice_error"):
        st.error(entry["notice_error"])
        return
    # 이해 확인 + 구체화 유도 표면 (파편 후속 질문 — 엔진 미호출 턴)
    if entry.get("coach"):
        st.markdown(f"질문을 이렇게 이해했어요: **‘{entry.get('frag', '')}’**")
        st.markdown("이 챗봇은 질문마다 **독립적으로** 답해요. 아래처럼 "
                    "구체적으로 물어보시면 정확한 사규를 찾아드립니다.")
        chips = entry.get("chips") or []
        for j, chip in enumerate(chips):
            if st.button(chip, key=f"coach_{idx}_{j}", use_container_width=True):
                st.session_state["pending_q"] = chip
                st.rerun()
        if not chips:
            st.caption("예: ‘클린신고 한도가 얼마인가요?’처럼 완전한 문장으로 "
                       "물어봐 주세요.")
        return
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
        # UNVERIFIED 문구 분기 (08-07 결함1 — grade 산식·action 무변경):
        # 문서명 실재 검증 전건 통과는 비차단이 보증(n_dm>0=block, 여기 도달
        # 자체가 통과). 섹션/문서 인용 존재는 표기 탐지로 판정 — verify 의
        # check_document_names 는 통과 항목을 기록하지 않아 cite_n 으론 불가.
        # 인용 부재·강등(앵커 실패)만 기존 강한 경고 유지.
        if (g == "UNVERIFIED" and not entry.get("degraded")
                and (entry.get("cite_n", 0) > 0
                     or _has_citation_form(entry.get("answer") or ""))):
            label = "사규 문서 대조 확인 — 세부 조항은 원문 참조"
        st.markdown(f'<span class="nx-grade {cls}">{label}</span>',
                    unsafe_allow_html=True)
    # 카테고리 뱃지 (v1 ui/render.py:142-165 — 접두어 최빈값)
    cat = _category_of(entry.get("ctx_titles") or [])
    if cat and not entry.get("critical"):
        st.markdown(f'<span class="nx-doc-chip">{_CAT_ICON.get(cat, "📌")} '
                    f'<b>{cat}</b> 카테고리</span>', unsafe_allow_html=True)
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
    if typing:
        st.write_stream(_typewriter(entry["answer"]))
    else:
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
            st.caption("AI가 답변을 생성한 검토 단계입니다. 답변 신뢰도 판단에 "
                       "참고하세요.")   # v1 app.py:1157 원문
    # 참고 사규 expander (v1 ui/render.py:296-312 — 발췌 escape)
    if entry.get("ctx_refs") and not entry.get("blocked"):
        with st.expander("참고 사규", expanded=False):
            for r in entry["ctx_refs"]:
                st.markdown(f"**{_h.escape(r['crumb'])}**")
                st.caption(_h.escape(r["snippet"]) + "…")
    # 응답 시간·피드백
    if entry.get("elapsed_s"):
        prov = str(entry.get("provider") or "").split(":")[-1]
        st.markdown(f'<p class="nx-meta">⏱️ 응답 {entry["elapsed_s"]}초'
                    + (f' · 🤖 {_h.escape(prov)}' if prov else "")
                    + "</p>", unsafe_allow_html=True)
    # PROACTIVE DOCK "다음 단계 예측" (v1 ui/feedback.py:112-140 이식)
    msgs = st.session_state.get("messages") or []
    orig_q = (msgs[idx - 1].get("content")
              if 0 < idx <= len(msgs) and msgs[idx - 1].get("role") == "user"
              else None)
    branch = _dock_branch(entry)
    rerolled: set = st.session_state.setdefault("rerolled", set())
    can_reroll = bool(orig_q) and idx not in rerolled
    if branch != "hidden":
        st.markdown('<div style="font-size:11.5px;font-weight:700;'
                    'letter-spacing:0.06em;color:#9A968D;margin:8px 0 6px 2px;">'
                    "다음 단계 예측</div>", unsafe_allow_html=True)
        dock_open: set = st.session_state.setdefault("dock_open", set())
        lbl = _DOCK_LABEL[branch] + (" 닫기" if idx in dock_open else "")
        if st.button(lbl, key=f"dock_{idx}", use_container_width=True):
            dock_open.symmetric_difference_update({idx})
            st.rerun()
        if idx in dock_open:
            _render_dock_panel(branch, _hotlines)
    if can_reroll:
        # v1 의 '다시 답변' — v2 는 단일 턴 설계라 동일 질문 재실행(새 턴)으로
        # 대응. prev_answer 컨텍스트 전달은 엔진 접촉이라 미이식.
        if st.button("🔄 다시 답변", key=f"reroll_{idx}", use_container_width=True):
            rerolled.add(idx)
            st.session_state["pending_q"] = orig_q
            st.rerun()
    if not entry.get("blocked"):
        # 피드백 3단계 플로우 (v1 ui/feedback.py:270-420 이식 — (A) CTA →
        # (B) 사유 pills + 자유 의견 + 제출/건너뛰기 → (C) 감사 캡션.
        # 영속화는 ADR-8 심의 대기, 세션+stderr 기록)
        fb_key = f"fb_{idx}"
        fb_state = st.session_state.get(fb_key)
        if fb_state == "done":
            st.caption("✅ 피드백 감사합니다.")
        elif fb_state in ("up", "down"):
            is_pos = fb_state == "up"
            sel = ("text-align:center;padding:8px 0;color:#1A1A1A;font-size:14px;"
                   "border:2px solid #1A1A1A;border-radius:4px;background:#fff;"
                   "font-weight:600;")
            off = ("text-align:center;padding:8px 0;color:#aaa;font-size:14px;"
                   "border:1px solid #eee;border-radius:4px;background:#fafafa;")
            ca, cb_ = st.columns(2)
            ca.markdown(f'<div style="{sel if is_pos else off}">'
                        f'{"✓ " if is_pos else ""}👍 도움됐어요</div>',
                        unsafe_allow_html=True)
            cb_.markdown(f'<div style="{sel if not is_pos else off}">'
                         f'{"✓ " if not is_pos else ""}👎 아쉬워요</div>',
                         unsafe_allow_html=True)
            reasons = st.pills(
                "어떤 점이 좋았나요? (복수 선택 가능)" if is_pos
                else "어떤 점이 아쉬웠나요? (복수 선택 가능)",
                options=_FB_REASONS_POS if is_pos else _FB_REASONS_NEG,
                selection_mode="multi", key=f"{fb_key}_reasons")
            comment = st.text_area(
                "자유 의견 (선택)", height=80,
                placeholder="구체적인 의견을 자유롭게 적어주세요 (선택)",
                key=f"{fb_key}_comment")
            c1, c2 = st.columns(2)
            if c1.button("제출", key=f"{fb_key}_submit", use_container_width=True):
                print(f"[ui:feedback] idx={idx} v={fb_state} "
                      f"reasons={list(reasons or [])} "
                      f"comment={(comment or '')[:300]!r}",
                      file=sys.stderr, flush=True)
                st.session_state[fb_key] = "done"
                st.rerun()
            if c2.button("건너뛰기", key=f"{fb_key}_skip", use_container_width=True):
                st.session_state[fb_key] = "done"
                st.rerun()
        else:
            st.markdown("**이 답변이 정확하고 도움이 되셨나요?**")
            st.caption("베타 단계입니다. 여러분의 피드백이 답변 품질 개선에 "
                       "직결됩니다.")   # v1 ui/feedback.py:314 원문
            c1, c2, _sp = st.columns([1, 1, 6])
            if c1.button("👍 도움됐어요", key=f"{fb_key}_up"):
                st.session_state[fb_key] = "up"
                print(f"[ui:feedback] idx={idx} v=up", file=sys.stderr, flush=True)
                st.rerun()
            if c2.button("👎 아쉬워요", key=f"{fb_key}_dn"):
                st.session_state[fb_key] = "down"
                print(f"[ui:feedback] idx={idx} v=down", file=sys.stderr, flush=True)
                st.rerun()
    # 클로징 멘트 (v1 personality closing_remark 이식)
    if not entry.get("blocked"):
        st.caption(_closing_line(bool(entry.get("critical")), idx))
    # 후속 질문 제안 (grounded — DB 실재 예시만, v1 render.py:207 문구)
    if entry.get("followups"):
        st.markdown("💡 **이런 질문도 해볼 수 있어요**")
        cols = st.columns(len(entry["followups"]))
        for j, (col, fq) in enumerate(zip(cols, entry["followups"])):
            if col.button(fq, key=f"fu_{idx}_{j}", use_container_width=True):
                st.session_state["pending_q"] = fq
                st.rerun()
    # 구체화 유도 (v1 core/prompts.py:296 규칙 3 문구의 표시 계층 이식 —
    # LLM 상황 리스트 생성은 합성 계약 접촉이라 정적 안내 + 위 grounded 칩이 담당)
    if not entry.get("critical"):
        st.caption("보다 구체적인 답변을 위해 상황(대상·시점·금액 등)을 함께 "
                   "적어 완전한 문장으로 질문해 주시면 도움이 됩니다.")


def _ask(question: str, status_cb=None) -> dict:
    """정본 파이프라인 1턴 실행 → 히스토리 엔트리 (엔진 무변경 배선).
    status_cb: 단계 전환 콜백 (F-1 대기 표면) — 파이프라인 호출 지점 사이에만
    삽입, 엔진 함수 시그니처·로직 무접촉."""
    from compass_engine.intake import run_intake
    from compass_engine.synthesis import synthesize
    from compass_engine.v1port.critical_mode import enforce_structure
    from compass_engine.verify import verify_answer

    cb = status_cb or (lambda *a: None)
    sb, ledger, retriever, hotlines, anchor_map = _engine()
    t0 = time.perf_counter()
    cb("analyze", None)
    intake = run_intake(sb, question)
    cb("search", None)
    res = retriever.retrieve(intake, {"tracks": ["rule"], "intent": "ui"})
    _seen: set[str] = set()
    _titles = [t for c in res["chunks"]
               if (t := (c.get("breadcrumb") or "").split(">")[0])
               and t not in _seen and not _seen.add(t)]
    cb("synthesize", _titles)
    syn = synthesize(intake["masked_text"], res["chunks"], anchor_map=anchor_map)
    cb("verify", None)
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
    ctx_refs = [{"crumb": c.get("breadcrumb") or "문서",
                 "snippet": (c.get("text") or "")[:180]}
                for c in res["chunks"][:8]]
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
        "ctx_refs": ctx_refs,
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
if not _consent_gate():   # 베타 동의 게이트 (운영 NEXUS_ENV=prod* 는 통과)
    st.stop()

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# ⏹ 생성 중지 처리 (v1 main() 상단 대응): 중지 클릭 → rerun 이 진행 런을
# 중단시켜 결과는 자연 폐기 — 여기서 플래그를 안내 엔트리로 전환한다.
if st.session_state.pop("_stop_requested", False):
    _msgs = st.session_state["messages"]
    if _msgs and _msgs[-1].get("role") == "user":
        _msgs.append({"role": "assistant", "notice":
                      "⏹ 생성이 중지되었습니다. 질문을 다시 입력해 주세요."})
    st.toast("⏹ 생성을 중지했습니다")

try:
    _hotlines = _engine()[3]
except Exception:
    _hotlines = {}
_sidebar(_hotlines)

# chat_input 은 항상 먼저 호출 (v1 app.py:1675-1685 상태 기계 이식) — 하단
# sticky 확보 + 첫 질문이 하단으로 와도 빈 홈 게이트에 반영. 처리 예정 질문
# (pending_q — v1 clicked_q 대응)이 있는 run 에서는 disabled 로 잠가 동시
# 제출이 진행 run 을 폐기하는 것을 원천 차단 (v1 PR-concurrent-guard).
_q_processing = bool(st.session_state.get("pending_q"))
q_input = st.chat_input("사규에 대해 물어보세요", disabled=_q_processing)
if q_input:
    # 인라인 처리 제거 (v1 app.py:1924-1929) — 하단 직접 입력도 pending_q
    # 경로로 통일 후 rerun. 처리 run 은 항상 _q_processing=True 로 렌더돼
    # 위젯 전부 잠긴 상태에서 합성이 돈다 → 합성 도중 재제출(진행 run 폐기)
    # 이 하단 경로에서도 원천 차단된다.
    st.session_state["pending_q"] = q_input
    st.rerun()
question = st.session_state.pop("pending_q", None)

# 빈 홈 — st.empty() placeholder 렌더 (v1 app.py:1690-1696 구조 가드 이식).
# 게이트에 question(하단 q_input + pending_q 합류)이 포함되어, 첫 질문이
# 어느 입력으로 와도 빈 홈이 답변과 동시에 렌더되지 않는다.
_home_ph = st.empty()
if not st.session_state["messages"] and not question:
    with _home_ph.container():
        # 빈 홈 한정: 하단 chat_input 숨김 (v1 ui/home.py:40-50 — 중앙 입력과
        # 중복 방지. 본 블록 미렌더 시 CSS 미주입 → 자동 원복, 조건부 분기 없음)
        st.markdown('<style>[data-testid="stChatInput"]'
                    "{display:none !important;}</style>",
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="nx-beta-bar">🛡️ 베타 서비스 — 입력 내용은 학습에 '
            "사용되지 않습니다. 자세한 안내는 좌측 사이드바 참조."
            "</div>", unsafe_allow_html=True)
        st.markdown(
            '<div class="nx-hero">'
            '<p class="nx-hero-eyebrow">사규의 나침반 · Compliance Compass</p>'
            '<p class="nx-hero-title">무엇을 확인해 드릴까요<span class="q">?</span></p>'
            '<p class="nx-hero-sub">' + _greeting_line()
            + " 신세계디에프 사규를 근거와 함께 안내합니다 — 상황을 그대로 적어 "
            "주셔도 됩니다.</p></div>",
            unsafe_allow_html=True)

        # 중앙 대형 입력 + 원형 레드 전송 (빈 홈의 유일한 가시 입력 — v1 정합)
        def _hero_submit() -> None:
            # Enter 제출 (v1 home.py:76-100 on_change 패턴) — 버튼과 동일 경로
            v = (st.session_state.get("hero_q") or "").strip()
            if v:
                st.session_state["pending_q"] = v

        ic, bc = st.columns([9, 1])
        hero_q = ic.text_input("질문", key="hero_q", label_visibility="collapsed",
                               placeholder="예: 협력사에서 선물을 받았는데 어떻게 해야 하나요?",
                               on_change=_hero_submit)
        if bc.button("↑", key="hero_go") and (hero_q or "").strip():
            st.session_state["pending_q"] = hero_q.strip()
            st.rerun()
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
    # 직전 실답변 (coach·notice 제외) — 파편 후속 질문 감지의 전제
    _prev = next((m for m in reversed(st.session_state["messages"])
                  if m.get("role") == "assistant"
                  and not m.get("coach") and not m.get("notice")), None)
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🧭"):
        if _is_fragment_followup(question, _prev is not None):
            # 이해 확인 + 구체화 유도 — 검색을 돌리지 않는다 (오답·오문서 방지).
            # 칩은 직전 답변 문서 기반 실재 예시(auto_query_examples)만.
            entry = {"role": "assistant", "coach": True, "frag": question,
                     "chips": (_prev.get("followups") or [])[:3]}
        elif not _check_rate_limit():
            limit = int(os.environ.get("NEXUS_DAILY_QUERY_LIMIT", "100"))
            entry = {"role": "assistant", "notice":
                     f"⚠️ 오늘 질의 한도({limit}회)를 초과했습니다. "
                     "베타 비용 가드 정책입니다. 내일 다시 이용해 주세요."}
        else:
            # F-1 대기 표면 (v1 app.py:702-820): 실시간 경과 타이머(iframe JS)
            # + 단계 전환 스피너 + ⏹ 생성 중지. 완료·실패 시 placeholder 정리.
            timer_ph = st.empty()
            prog_ph = st.empty()
            stop_ph = st.empty()
            with timer_ph.container():
                _nx_iframe(_TIMER_HTML, height=60)
            prog_ph.markdown(_spinner_html("질문 분석 중…", "핵심 쟁점·도메인 파악"),
                             unsafe_allow_html=True)
            with stop_ph.container():
                st.button("⏹ 생성 중지", key="_stop_gen_btn",
                          on_click=_request_stop, use_container_width=True)

            def _stage(stage: str, payload) -> None:
                if stage == "search":
                    prog_ph.markdown(
                        _spinner_html("관련 사규 탐색 중…", "근거 조항 검색"),
                        unsafe_allow_html=True)
                elif stage == "synthesize":
                    titles = payload or []
                    shown = titles[:2]
                    more = len(titles) - len(shown)
                    t = ", ".join(shown) + (f" 외 {more}건" if more > 0 else "")
                    sub = (f"근거 사규: {t}" if t
                           else "검색 결과 없음 — 답변에 한계가 있을 수 있어요")
                    prog_ph.markdown(_spinner_html("답변 작성 중…", sub, cycle=True),
                                     unsafe_allow_html=True)
                elif stage == "verify":
                    prog_ph.markdown(
                        _spinner_html("답변 검증 중…", "인용 원장 대조"),
                        unsafe_allow_html=True)

            try:
                entry = _ask(engine_q, status_cb=_stage)
            except Exception as e:
                print(f"[ui:error] {type(e).__name__}: {e}",
                      file=sys.stderr, flush=True)
                # 영속 안내 엔트리 — 아래 마무리 rerun 후에도 replay 로 표출
                entry = {"role": "assistant", "notice_error":
                         "일시적인 오류로 답변을 만들지 못했습니다. 잠시 후 "
                         "다시 시도해 주세요. 계속되면 담당 부서(CSR팀)에 "
                         "알려주세요."}
            finally:
                timer_ph.empty()
                prog_ph.empty()
                stop_ph.empty()
        if entry is not None:
            # 타이핑 재생은 이 run 에서 재생 (엔진 답변만) — 정적 엔트리는
            # 아래 rerun 후 replay 가 렌더
            if not (entry.get("coach") or entry.get("notice")
                    or entry.get("notice_error")):
                _render_assistant(entry, idx=len(st.session_state["messages"]),
                                  typing=True)
            st.session_state["messages"].append(entry)
    # 처리 완료 → 즉시 다음 cycle 복귀 (v1 app.py:1913) — pending_q 가 비워진
    # 상태로 재렌더되어 chat_input 잠금 해제. 잠금은 처리 run 프레임에만 존재.
    st.rerun()
