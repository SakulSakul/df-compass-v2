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
    # 사용자 화면 구성: 히어로 + 예시 3개 + 입력창 + 브랜드/디스클레이머
    # (클래스명은 CSS 주입 문자열에도 있어 실문안으로 판정)
    assert "사규, 물어보면 바로 나침반" in html
    assert "nx-brand" in html
    assert "nx-disclaimer" in html
    assert len(at.button) == 3
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
    assert "사규, 물어보면 바로 나침반" not in _all_markdown(at)
