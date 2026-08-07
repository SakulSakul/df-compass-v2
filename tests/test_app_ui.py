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


def _at(monkeypatch, *, env: str = "prod-test") -> AppTest:
    # 엔진 초기화가 네트워크로 나가지 않도록 env 제거 → hotlines fallback 경로
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    # 동의 게이트는 전용 테스트에서 검증 — 기본은 prod(게이트 해제)로 본 화면
    monkeypatch.setenv("NEXUS_ENV", env)
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
    assert "무엇을 확인해 드릴까요" in html   # 물음표는 레드 span 분리
    assert "학습에 사용되지 않습니다" in html   # 전폭 베타 배너
    assert "드릴까요?." not in html              # 오타 회귀 방지 (::after 버그)
    assert len(at.selectbox) == 1          # 질의 범위 필터
    assert "nx-brand" in html
    assert "nx-disclaimer" in html
    assert len(at.button) == 7   # 예시 6 + 히어로 전송
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
    assert "무엇을 확인해 드릴까요" not in _all_markdown(at)


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
         "ctx_refs": [{"crumb": "(CSR) 대외출강 운영 지침>제3조",
                       "snippet": "제3조(승인) 외부 강의는 사전승인 대상"}],
         "cite_ok": 1, "cite_n": 1, "followups": ["강사료는 어떻게 처리하나요?"],
         "elapsed_s": 12.3, "provider": "gemini:g-3.6",
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
    # 결함1(08-07): UNVERIFIED + 인용 존재·비강등 → 중립 톤 라벨 (a)
    assert "사규 문서 대조 확인" in html
    assert "조항 단위 근거 미확인" not in html
    assert "참고 규정" in html                             # 참고 인용 구획 캡션
    assert "📄" in html                                    # 출처 문서 칩
    assert "응답 12.3초" in html and "🤖" in html          # ⏱·🤖 표기
    labels = [str(e.label) for e in at.expander]
    assert any("AI 검토 과정" in l for l in labels)
    assert any("참고 사규" in l for l in labels)             # 참고 사규 expander
    caps = " ".join(str(c.value) for c in at.caption)
    assert "검토 단계입니다" in caps                         # v1 캡션 문구
    assert "이 답변이 정확하고 도움이 되셨나요?" in html      # 피드백 플로우 문구
    assert "베타 단계입니다" in caps                         # v1 피드백 캡션 (검산 지적①)
    assert "이런 질문도 해볼 수 있어요" in html               # 💡 후속 제안 문구
    assert "CSR" in html and "카테고리" in html              # 카테고리 뱃지
    assert any(m in caps for m in ("좋은 하루", "언제든", "도움이 되었길"))  # 클로징
    # PROACTIVE DOCK (결함4 재설계): CSR 카테고리 → 클린신고 분기.
    # UNVERIFIED(안전 카테고리) 답변은 확신 없음 → 주 액션 생략 (오안내<무안내)
    assert "다음 단계 예측" in html
    btns = [str(b.label) for b in at.button]
    assert any("클린신고 안내" in b for b in btns)
    assert not any("인사교육팀 문의" in b for b in btns)
    assert any("다시 답변" in b for b in btns)
    assert "보다 구체적인 답변을 위해" in caps               # 구체화 유도 (규칙3 문구)


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


def test_consent_gate_beta(monkeypatch):
    """베타 env → 동의서 화면만, 본 화면 차단. 세션 통과 플래그 → 본 화면."""
    at = _at(monkeypatch, env="beta-personal")
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    assert "베타 참가 동의서" in html
    assert "무엇을 확인해 드릴까요" not in html            # 본 화면 미노출
    assert len(at.chat_input) == 0                        # 챗 입력도 차단
    assert any("동의하고 시작" in str(b.label) for b in at.button)
    # 세션 통과 플래그 → 게이트 통과, 본 화면 렌더
    at2 = _at(monkeypatch, env="beta-personal")
    at2.session_state["beta_consent_v"] = "v1"
    at2.run()
    assert not at2.exception
    assert "무엇을 확인해 드릴까요" in _all_markdown(at2)


def test_rate_limit_guard(monkeypatch):
    """비용 가드: 한도 0 → 엔진 미호출로 경고 안내 (오프라인에서 예외 없이)."""
    monkeypatch.setenv("NEXUS_DAILY_QUERY_LIMIT", "0")
    at = _at(monkeypatch)
    at.run()
    at.chat_input[0].set_value("법인카드 사용 기준이 어떻게 되나요?").run()
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "질의 한도(0회)를 초과" in warns
    assert "베타 비용 가드" in warns
    # 안내가 히스토리에 영속 (notice 엔트리)
    assert any(m.get("notice") for m in at.session_state["messages"])


def test_fragment_coach_surface(monkeypatch):
    """파편 후속 질문 → 엔진을 돌리지 않고 이해 확인 + 구체화 칩 (실재 예시만).
    오프라인에서 예외 없이 통과 = 검색·합성 미호출 증명."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "클린신고 제도가 뭔가요?"},
        {"role": "assistant", "answer": "클린신고는 자진 신고 제도입니다.",
         "blocked": False, "critical": False, "degraded": False,
         "grade": "HIGH", "card": None, "ctx_titles": [],
         "cite_ok": 1, "cite_n": 1, "n_chunks": 3, "timings": {}, "retries": 0,
         "followups": ["클린신고 한도가 얼마인가요?"]},
    ]
    at.run()
    at.chat_input[0].set_value("그럼 얼마까지 되는데?").run()
    assert not at.exception
    html = _all_markdown(at)
    assert "질문을 이렇게 이해했어요" in html
    assert "독립적으로" in html                            # 단일 턴 안내
    assert any("클린신고 한도가 얼마인가요?" in str(b.label) for b in at.button)
    assert any(m.get("coach") for m in at.session_state["messages"])


def _entry(**kw) -> dict:
    base = {"role": "assistant", "answer": "일반 안내 본문입니다.",
            "blocked": False, "critical": False, "degraded": False,
            "grade": "UNVERIFIED", "card": None, "ctx_titles": [],
            "cite_ok": 0, "cite_n": 1, "n_chunks": 3, "timings": {},
            "retries": 0, "followups": [], "elapsed_s": 5.0}
    base.update(kw)
    return base


def test_unverified_label_branches(monkeypatch):
    """결함1(08-07): (a) 인용 존재(앵커 카운트 또는 문서수준 표기)·비강등 →
    중립 톤 / (b) 인용 부재 또는 강등 → 강한 경고 유지. 산식·action 무접촉."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q1"},
        _entry(cite_n=1),                       # (a) 앵커 카운트 경로
        {"role": "user", "content": "q2"},
        _entry(cite_n=0, answer="사용 기준 안내.\n\n[참조: (재무) 법인카드 관리 지침]"),
        {"role": "user", "content": "q3"},      # ↑ (a) 문서수준 표기 경로
        _entry(cite_n=0),                       # (b) 인용 자체 부재
        {"role": "user", "content": "q4"},
        _entry(cite_n=1, degraded=True, grade="UNVERIFIED"),  # (b) 강등
    ]
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    assert html.count("사규 문서 대조 확인 — 세부 조항은 원문 참조") == 2  # (a)×2
    assert html.count("조항 단위 근거 미확인 — 원문 확인 권장") == 2      # (b)×2


def test_dock_category_mapping(monkeypatch):
    """결함4(08-07): 카테고리 결정론 매핑 — 재무→경리팀·경영관리팀 /
    인사→인사교육팀 / 무매핑(안전)→주 액션 생략 (오안내<무안내)."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "법인카드 사용 기준이 어떻게 되나요?"},
        _entry(ctx_titles=["(재무) 법인카드 관리 지침"]),
        {"role": "user", "content": "연차는 어떻게 신청하나요?"},
        _entry(ctx_titles=["(인사) 취업규칙"]),
        {"role": "user", "content": "공기질 관리 기준은?"},
        _entry(ctx_titles=["(안전) 공기질 유지관리 지침"]),
    ]
    at.run()
    assert not at.exception
    btns = [str(b.label) for b in at.button]
    assert any("경리팀·경영관리팀" in b for b in btns)      # 재무 매핑
    assert any("인사교육팀 문의" in b for b in btns)        # 인사 매핑
    # 재무 답변에 인사 패널 미표출 — dock 주 액션은 엔트리당 1개, hr 은 인사만
    assert sum(1 for b in btns if "인사교육팀" in b) == 1
    # 무매핑 카테고리는 주 액션 생략 (dock 키 3개 중 안전용 없음)
    assert sum(1 for b in btns
               if any(t in b for t in ("문의", "안내"))) == 2


def test_theme_pinned_light():
    """결함2·3(08-07) 근본 수정 가드: 테마 라이트 고정 (config.toml).
    다크 모드 브라우저에서 emotion 텍스트 색(백색)이 주입 CSS 의 라이트
    배경 위에 얹혀 빈 항목처럼 보이는 결함 — 재발 방지 고정."""
    cfg = (ROOT / ".streamlit" / "config.toml").read_text()
    assert 'base = "light"' in cfg
    assert 'textColor' in cfg


def test_motion_css_present(monkeypatch):
    """F 계급(시간축) 보조 검증 — 모션 자체는 녹화/연속 캡처가 정본이고,
    AppTest 는 keyframes·THINKING 블록 CSS 의 존재만 고정한다."""
    at = _at(monkeypatch)
    at.run()
    html = _all_markdown(at)
    for token in ("nx-spin", "nx-pulse", "nx-cycle", "nx-think"):
        assert token in html


def test_stop_flag_to_notice(monkeypatch):
    """⏹ 생성 중지: 플래그 → 다음 런에서 안내 엔트리 전환 + 플래그 소거."""
    at = _at(monkeypatch)
    at.session_state["_stop_requested"] = True
    at.session_state["messages"] = [{"role": "user", "content": "질문"}]
    at.run()
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "생성이 중지되었습니다" in warns
    assert "_stop_requested" not in at.session_state


def test_feedback_reason_flow(monkeypatch):
    """피드백 (A)→(B)→(C): 👍 클릭 → 사유 pills·자유 의견·제출 → 감사 캡션
    (v1 feedback.py:270-420 플로우)."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q"}, _entry(cite_n=1)]
    at.run()
    up = next(b for b in at.button if "👍 도움됐어요" in str(b.label))
    up.click().run()
    # (B) 표면: 사유 pills(button_group)·자유 의견·제출/건너뛰기
    assert any("자유 의견" in str(t.label) for t in at.text_area)
    assert any("제출" == str(b.label) for b in at.button)
    assert any("건너뛰기" == str(b.label) for b in at.button)
    submit = next(b for b in at.button if str(b.label) == "제출")
    submit.click().run()
    caps = " ".join(str(c.value) for c in at.caption)
    assert "피드백 감사합니다" in caps


def test_hero_enter_submit(monkeypatch):
    """히어로 입력 Enter 제출 (v1 home.py on_change 패턴) — 값 변경만으로
    질문이 제출되어 처리 경로에 진입한다 (오프라인 → 에러 표면 = 진입 증명)."""
    at = _at(monkeypatch)
    at.run()
    at.text_input(key="hero_q").set_value("법인카드 기준 알려줘").run()
    html = _all_markdown(at)
    assert "법인카드 기준 알려줘" in html              # user 말풍선
    errs = " ".join(str(e.value) for e in at.error)
    assert "일시적인 오류" in errs                    # 엔진 경로 진입


def test_fragment_noop_without_prev(monkeypatch):
    """직전 턴이 없으면 파편형 문자열도 가로채지 않는다 (no-op 폴백) —
    정상 경로로 진입해 오프라인 에러 표면이 뜨는 것으로 증명."""
    at = _at(monkeypatch)
    at.run()
    at.chat_input[0].set_value("그럼 얼마까지 되는데?").run()
    assert not at.exception
    assert "질문을 이렇게 이해했어요" not in _all_markdown(at)
    errs = " ".join(str(e.value) for e in at.error)
    assert "일시적인 오류" in errs                         # 엔진 경로 진입 증명
