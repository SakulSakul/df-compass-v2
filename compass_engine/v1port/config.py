"""v1port shim — v1 core/config.py 에서 critical 경로가 쓰는 부분만 발췌 복사.

get_secret / _DEFAULT_HOTLINES / load_hotlines / hr_routing_line 은 v1 원문
그대로 (Phase 1 ⑧ 무수정 이식 — 동작 보존이 목적, streamlit secrets 분기는
env 폴백과 동일 semantics 라 그대로 둠).
"""
from __future__ import annotations

import os
from typing import Any


def get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st  # type: ignore
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


# ── Hotline / 안내 문구 (DB 우선, fallback default) — v1 원문 복사 ──
_DEFAULT_HOTLINES: dict[str, str] = {
    "internal_report_url": "https://example.invalid/report",
    "external_hotline":    "고용노동부 1350",
    "ethics_hotline_url":  "https://example.invalid/ethics",
    "hr_contact_text":     "인사 규정·복리후생 등 인사 행정 사항은 인사교육팀에 문의해 주시기 바랍니다.",
    "hr_chatbot_url":      "",
}


def load_hotlines(supabase: Any | None = None) -> dict[str, str]:
    out = dict(_DEFAULT_HOTLINES)
    if supabase is None:
        return out
    try:
        rows = supabase.table("hotline_config_public").select("key,value").execute().data or []
        for r in rows:
            k = r.get("key"); v = r.get("value")
            if k and v is not None and str(v).strip():
                out[k] = v
    except Exception:
        pass
    return out


def hr_routing_line(hotlines: dict[str, str]) -> str:
    """인사 챗봇 오픈 시 자연스러운 전환을 위한 단일 문구 빌더."""
    url = (hotlines.get("hr_chatbot_url") or "").strip()
    if url:
        return f"인사 챗봇으로 이동: {url}"
    return hotlines.get("hr_contact_text") or _DEFAULT_HOTLINES["hr_contact_text"]
