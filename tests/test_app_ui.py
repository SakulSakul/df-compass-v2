"""사용자용 UI 오프라인 테스트 (AppTest — 네트워크 차단 상태).

안전 표면 불변 조건(백로그 항목, 위반 시 H 정지)을 렌더 수준에서 고정:
- blocked 답변 미표출 + 차단 안내
- critical 배너 가시성
- degrade 칩 가시성
빌더 배지·개발용 칩 제거도 함께 고정한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _at(monkeypatch) -> AppTest:
    # 엔진 초기화가 네트워크로 나가지 않도록 env 제거 → hotlines fallback 경로
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=15)


def _all_markdown(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def test_home_user_facing_no_dev_surface(monkeypatch):
    at = _at(monkeypatch)
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    # 빌더 배지·개발용 표시 제거
    assert "BUILDER PREVIEW" not in html
    assert "내부 검증 전용" not in html
    assert "confidence" not in html
    # 사용자 화면 구성 (UI 패리티 08-06): v1 히어로 문안 + 베타 배너 +
    # 예시 6개 + 질의 범위 + 입력창 (클래스명은 CSS 에도 있어 실문안 판정)
    assert "무엇을 확인해 드릴까요?" in html
    assert "학습에 사용되지 않습니다" in html
    assert len(at.selectbox) == 1          # 질의 범위 필터
    assert "nx-brand" in html
    assert "nx-disclaimer" in html
    assert len(at.button) == 6
    assert len(at.chat_input) == 1


def test_safety_surface_replay(monkeypatch):
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "answer": "유출되면 안 되는 본문",
         "blocked": True, "critical": False, "degraded": False},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "answer": "위험 상황 답변 본문",
         "blocked": False, "critical": True, "degraded": True},
    ]
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    # ① blocked → 답변 미표출 (본문이 화면 어디에도 없어야) + 차단 안내
    assert any("차단되었습니다" in str(e.value) for e in at.error)
    assert "유출되면 안 되는 본문" not in html
    # ② critical → 배너 가시성
    assert "nx-critical" in html and "심각 사안 감지" in html
    # ③ degrade → 칩 가시성 + 답변은 표출
    assert "신뢰도 강등" in html
    assert "위험 상황 답변 본문" in html


def test_hero_hidden_after_history(monkeypatch):
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "answer": "답", "blocked": False,
         "critical": False, "degraded": False},
    ]
    at.run()
    assert not at.exception
    assert "무엇을 확인해 드릴까요?" not in _all_markdown(at)


def test_parity_surfaces_replay(monkeypatch):
    """UI 패리티(08-06): grade 라벨·판정 카드·참고 인용 구획·출처 칩·검토
    과정·응답 시간 — replay 오프라인 고정. 안전 표면과 공존 확인."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q1"},
        {"role": "assistant",
         "answer": "질문하신 내용\n**핵심 결론**\n조건부로 가능합니다 — 사전 승인이 필요합니다.\n\n**📋 사규 기준**\n- 외부 강의는 사전승인 대상입니다.\n\n**권장 행동**\nx\n\n[참조: (CSR) 대외출강 운영 지침]",
         "blocked": False, "critical": False, "degraded": False,
         "grade": "HIGH",
         "card": {"stance": "조건부", "label": "조건부로 가능합니다 — 사전 승인이 필요합니다.",
                  "quote": "외부 강의는 사전승인 대상입니다.",
                  "cite": "(CSR) 대외출강 운영 지침 제3조"},
         "ctx_titles": ["(CSR) 대외출강 운영 지침"],
         "cite_ok": 1, "cite_n": 1, "followups": [],
         "elapsed_s": 12.3, "provider": "gemini:x",
         "timings": {"rpc_ms": 2000, "rerank_ms": 1000},
         "router_hit": True, "n_chunks": 5, "retries": 0},
        {"role": "user", "content": "q2"},
        {"role": "assistant",
         "answer": "해당 내용은 사규에서 확인되지 않습니다. 참고로 관련 규정이 있습니다.",
         "blocked": False, "critical": False, "degraded": False,
         "grade": "UNVERIFIED", "card": None,
         "ctx_titles": ["(안전) 공기질 유지관리 지침"],
         "cite_ok": 1, "cite_n": 1, "followups": [],
         "elapsed_s": 8.0, "n_chunks": 3, "timings": {}, "router_hit": None,
         "retries": 0},
    ]
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    assert "✓ 사규 원문 근거 확인" in html                 # HIGH 라벨
    assert "조건부로 가능합니다" in html                    # 판정 카드 pill
    assert "📕" in html and "제3조" in html               # 카드 출처
    assert "조항 단위 근거 미확인" in html                  # UNVERIFIED 라벨
    assert "참고 규정" in html                             # 참고 인용 구획 캡션
    assert "📄" in html                                    # 출처 문서 칩
    assert "응답 12.3초" in html
    assert any("AI 검토 과정" in str(e.label) for e in at.expander)


def test_parity_absent_on_safety_paths(monkeypatch):
    """blocked 는 패리티 표면 전체 미표출, critical 은 카드·grade 미표출
    (안전 표면 우선 — 배너+4단 구조 방해 금지)."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "answer": "본문", "blocked": True,
         "critical": False, "degraded": False, "grade": "HIGH",
         "card": {"stance": "허용", "label": "x", "quote": "", "cite": ""},
         "ctx_titles": ["문서"], "cite_ok": 1, "cite_n": 1,
         "elapsed_s": 5.0, "n_chunks": 3},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "answer": "critical 답변", "blocked": False,
         "critical": True, "degraded": True, "grade": "LOW", "card": None,
         "ctx_titles": ["(인사) 성희롱 예방 지침"], "cite_ok": 0, "cite_n": 2,
         "elapsed_s": 9.0, "n_chunks": 4, "timings": {}, "retries": 0},
    ]
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    assert "본문" not in html                              # blocked 미표출 불변
    assert "✓ 사규 원문 근거 확인" not in html              # blocked 라벨 미표출
    assert "심각 사안 감지" in html and "신뢰도 강등" in html  # 안전 표면 유지
