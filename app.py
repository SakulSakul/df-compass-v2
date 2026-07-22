"""DF COMPASS v2 · 최소 UI (Phase 1 ⑨ — 빌더 본인 전용).

정본 파이프라인 배선: intake(critical 게이트·pii) → retrieve(v4-ctx + rerank
+ 이웃결합) → synthesize(섹션 계약, 3.6 확정) → verify(§5 결정론) → render.
- verify action=block 이면 답변을 내보내지 않는다 (품질 서열 1위).
- critical 이면 enforce_structure(4단 + 핫라인 박스) + 상단 배너.
- Warm Editorial 팔레트 (v1 디자인 시스템 축약 이식).

secrets/env: SUPABASE_URL, SUPABASE_KEY(anon), GEMINI_API_KEY
(원장 로드는 anon SELECT — RLS 미부여 시 service key 를 SUPABASE_SERVICE_KEY 로)
"""
from __future__ import annotations

import os
import sys
import time

import streamlit as st

st.set_page_config(page_title="DF COMPASS v2 · builder preview",
                   page_icon="🧭", layout="centered")

_CSS = """
<style>
:root { --accent:#C8102E; --ink:#1F1E1D; --caption:#7A766E;
        --surface:#F4F1EB; --border:#E7E3DC; }
.v2-badge { display:inline-block; font-size:11px; font-weight:700;
  letter-spacing:.08em; color:#fff; background:var(--accent);
  border-radius:6px; padding:3px 10px; margin-bottom:4px; }
.v2-head { display:flex; align-items:center; gap:10px; margin:2px 0 14px; }
.v2-head .dot { width:8px; height:8px; border-radius:50%; background:var(--accent); }
.v2-head b { font-size:14px; letter-spacing:.06em; color:var(--ink); }
.v2-head .rule { flex:1; height:1px; background:var(--border); }
.v2-chip { display:inline-block; font-size:12px; font-weight:700;
  border-radius:6px; padding:3px 10px; margin-right:6px;
  background:var(--surface); color:#5F5E5A; }
.v2-chip.warn { background:#FCEEF0; color:#8A1020; border:1px solid var(--accent); }
.v2-crit { display:flex; gap:8px; padding:10px 12px; margin:8px 0 12px;
  background:#FCEEF0; border:1px solid var(--accent); border-radius:8px;
  font-size:13px; color:#8A1020; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)
st.markdown('<span class="v2-badge">V2 BUILDER PREVIEW — 내부 검증 전용</span>',
            unsafe_allow_html=True)
st.markdown('<div class="v2-head"><span class="dot"></span>'
            '<b>DF COMPASS v2</b><span class="rule"></span></div>',
            unsafe_allow_html=True)


@st.cache_resource(show_spinner="엔진 초기화 중…")
def _engine():
    from supabase import create_client
    from compass_engine.registry import load_ledger
    from compass_engine.reranker import GeminiReranker
    from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn

    url = os.environ["SUPABASE_URL"]
    anon = os.environ.get("SUPABASE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    sb = create_client(url, anon)
    ledger_key = os.environ.get("SUPABASE_SERVICE_KEY") or anon
    ledger = load_ledger(create_client(url, ledger_key))
    retriever = V1RpcRetriever(
        sb, gemini_embed_fn(), top_k=3,
        rpc_name="nexus_hybrid_search_v4_ctx",
        expand_neighbors=True, reranker=GeminiReranker(),
    )
    return sb, ledger, retriever


question = st.chat_input("사규에 대해 물어보세요 (빌더 전용 프리뷰)")
if question:
    from compass_engine.intake import run_intake
    from compass_engine.synthesis import synthesize
    from compass_engine.v1port.config import load_hotlines
    from compass_engine.v1port.critical_mode import enforce_structure
    from compass_engine.verify import verify_answer

    sb, ledger, retriever = _engine()
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🧭"):
        t0 = time.perf_counter()
        with st.status("파이프라인 실행 중…", expanded=False) as status:
            st.write("① intake — PII 마스킹 · critical 판정")
            intake = run_intake(sb, question)
            st.write("② retrieve — v4-ctx + rerank + 이웃결합")
            res = retriever.retrieve(intake, {"tracks": ["rule"], "intent": "ui"})
            st.write("③ synthesize — 섹션 계약")
            syn = synthesize(intake["masked_text"], res["chunks"])
            st.write("④ verify — §5 결정론 대조")
            verdict = verify_answer(syn.answer_md, ledger)
            status.update(label="완료", state="complete")

        if intake["is_critical"]:
            st.markdown(
                '<div class="v2-crit">🚨 <b>심각 사안 감지</b> — 핫라인 우선 '
                "안내가 포함됩니다. 실제 응급상황은 즉시 핫라인을 이용하세요.</div>",
                unsafe_allow_html=True)
            answer = enforce_structure(
                base_answer=syn.answer_md, kind=intake["critical_kind"] or "safety",
                action_items=None, hotlines=load_hotlines(sb))
        else:
            answer = syn.answer_md

        if verdict["action"] == "block":
            st.error("이 답변은 비실재 문서 인용이 감지되어 차단되었습니다 (§5). "
                     "질문을 바꿔 다시 시도하거나 담당 부서에 문의해 주세요.")
        else:
            if verdict["action"] == "degrade":
                st.markdown('<span class="v2-chip warn">⚠ 인용 일부 미검증 — '
                            "신뢰도 강등</span>", unsafe_allow_html=True)
            st.markdown(answer)

        ok_n = sum(1 for c in verdict["citations"] if c["verdict"] == "ok")
        st.markdown(
            f'<span class="v2-chip">검증 인용 {ok_n}/{len(verdict["citations"])}</span>'
            f'<span class="v2-chip">confidence {verdict["confidence"]:.2f}</span>'
            f'<span class="v2-chip">{res["provider"]}</span>'
            f'<span class="v2-chip">{syn.provider}</span>'
            f'<span class="v2-chip">{(time.perf_counter()-t0):.1f}s</span>',
            unsafe_allow_html=True)
        # trace — 로컬 로그 (ADR-8: DB 쓰기 금지)
        print(f"[ui:trace] q_len={len(question)} critical={intake['is_critical']} "
              f"chunks={len(res['chunks'])} action={verdict['action']} "
              f"conf={verdict['confidence']}", file=sys.stderr, flush=True)
