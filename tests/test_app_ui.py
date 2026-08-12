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
    assert len(at.button) == 4   # 추천 필 3 (v1 정합) + 히어로 전송
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
    assert "🟢 높은 신뢰도" in html                        # HIGH — 메타 행 (002-C)
    assert "조건부로 가능합니다" in html                    # 판정 카드 pill
    assert "📕" in html and "제3조" in html               # 카드 출처
    # 결함1(08-07): UNVERIFIED + 인용 존재·비강등 → 중립 톤 라벨 (a)
    assert "사규 문서 대조 확인" in html
    assert "조항 단위 근거 미확인" not in html
    assert "참고 규정" in html                             # 참고 인용 구획 캡션
    assert "📄" in html                                    # 출처 문서 칩
    assert "응답 12.3초" in html and "🤖" in html          # ⏱·🤖 표기
    # 002-C: 카테고리는 하단 메타 행에만 — 엔트리당 1회 (상단 뱃지 제거)
    assert html.count("카테고리") == 2                     # 엔트리 2건 각 1회
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
    assert "높은 신뢰도" not in html                        # blocked 등급 미표출
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
    """카테고리 결정론 매핑 (트랙C 개정): 재무→경리팀·경영관리팀 / 무매핑
    (안전·인사 카테고리 단독)→주 액션 생략 — hr dock 은 답변 내 인사 안내
    문구(_A_HR_KW) 신호로만 발동 (v1 정합, 오안내<무안내)."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "법인카드 사용 기준이 어떻게 되나요?"},
        _entry(ctx_titles=["(재무) 법인카드 관리 지침"]),
        {"role": "user", "content": "연차는 어떻게 신청하나요?"},
        # 인사 카테고리 + 인사 문구 없는 일반 답변 → hidden (nomatch 오안내 방지)
        _entry(ctx_titles=["(인사) 취업규칙"]),
        {"role": "user", "content": "복리후생 규정이 궁금해요"},
        # 답변에 인사 안내 문구 → hr 발동 (v1 답변 신호 경로)
        _entry(ctx_titles=["(인사) 취업규칙"],
               answer="인사 규정·복리후생 등 인사 행정 사항은 "
                      "인사교육팀에 문의해 주시기 바랍니다."),
        {"role": "user", "content": "공기질 관리 기준은?"},
        _entry(ctx_titles=["(안전) 공기질 유지관리 지침"]),
    ]
    at.run()
    assert not at.exception
    btns = [str(b.label) for b in at.button]
    assert any("경리팀·경영관리팀" in b for b in btns)      # 재무 매핑
    # hr 은 문구 신호 건 1건만 — 인사 카테고리 단독 건은 미발동
    assert sum(1 for b in btns if "인사교육팀 문의" in b) == 1
    # dock 주 액션 총량 = 재무 1 + hr(문구) 1 (안전·인사 단독은 생략)
    assert sum(1 for b in btns
               if any(t in b for t in ("문의", "안내"))) == 2


def test_dock_fair_trade_deterministic(monkeypatch):
    """공정거래 결정론 (v1 REPORT_DOC_DOMAINS — nexus_button_branch.py:47):
    최빈값이든 소수 혼합이든 근거 문서 집합에 공정거래가 있으면 report.
    기존 4종 매핑 회귀 없음은 test_dock_category_mapping 이 담당."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "협력사 지정은 어떻게 하나요?"},
        _entry(ctx_titles=["(공정거래) 하도급 거래 공정화 지침"]),
        {"role": "user", "content": "경비 처리 기준 알려줘"},
        # 공정거래가 최빈이 아닌 혼합 케이스 — v1 contexts-단독 케이스 보존
        _entry(ctx_titles=["(재무) 일반경비 처리지침", "(재무) 예산합의 관리 지침",
                           "(공정거래) 하도급 거래 공정화 지침"]),
    ]
    at.run()
    assert not at.exception
    btns = [str(b.label) for b in at.button]
    assert sum(1 for b in btns if "신고 방법 안내" in b) == 2   # 두 건 모두 report
    assert not any("경리팀" in b for b in btns)                # 혼합 건도 finance 아님


def test_theme_pinned_light():
    """결함2·3(08-07) 근본 수정 가드: 테마 라이트 고정 (config.toml).
    다크 모드 브라우저에서 emotion 텍스트 색(백색)이 주입 CSS 의 라이트
    배경 위에 얹혀 빈 항목처럼 보이는 결함 — 재발 방지 고정."""
    cfg = (ROOT / ".streamlit" / "config.toml").read_text()
    assert 'base = "light"' in cfg
    assert 'textColor' in cfg


_HIDE_CSS = '[data-testid="stChatInput"]{display:none !important;}'
_WIDTH_CSS = "max-width:960px !important"    # 빈 홈 한정 폭 제한 (v1 home.py:45)


def test_single_input_state_machine(monkeypatch):
    """빈 홈 입력창 이중화 해소 (v1 상태 기계): 빈 홈 = 히어로 입력만
    (하단 chat_input 은 CSS 숨김), 대화 후 = 하단 입력만 (숨김 CSS 자동
    원복 + 히어로 부재). chat_input 은 두 상태 모두 항상 호출된다."""
    at = _at(monkeypatch)
    at.run()
    html = _all_markdown(at)
    assert _HIDE_CSS in html                       # 빈 홈: 하단 입력 숨김 마커
    assert _WIDTH_CSS in html                      # 빈 홈: 960px 폭 제한 마커
    assert "무엇을 확인해 드릴까요" in html          # 히어로 존재
    assert len(at.chat_input) == 1                 # 항상 호출 (제거 아님)
    # 1문답 후 — 숨김·폭 CSS 미주입(자동 원복) + 히어로 부재 + chat_input 존재
    at2 = _at(monkeypatch)
    at2.session_state["messages"] = [
        {"role": "user", "content": "q"}, _entry(cite_n=1)]
    at2.run()
    html2 = _all_markdown(at2)
    assert _HIDE_CSS not in html2
    assert _WIDTH_CSS not in html2
    assert "무엇을 확인해 드릴까요" not in html2
    assert len(at2.chat_input) == 1
    assert not at2.chat_input[0].disabled


def test_chat_input_submit_unified_via_pending(monkeypatch):
    """v1 '인라인 처리 제거' 불변식 (app.py:1924-1929 + :1913): 하단 제출은
    pending_q 적재 + rerun 으로 통일 — 처리 run(잠금 프레임)은 과도 상태라
    라이브 실측이 정본이고, AppTest 는 완주 결과를 고정한다: 오류가 영속
    엔트리로 남고(마무리 rerun 생존), pending 소비 완료, 입력 잠금 해제 복귀."""
    at = _at(monkeypatch)
    at.run()
    at.chat_input[0].set_value("법인카드 사용 기준이 어떻게 되나요?").run()
    assert not at.exception
    assert "법인카드 사용 기준" in _all_markdown(at)      # user 말풍선
    errs = " ".join(str(e.value) for e in at.error)
    assert "일시적인 오류" in errs                        # 처리 경로 진입 증명
    assert any(m.get("notice_error")                      # 영속 엔트리 (rerun 생존)
               for m in at.session_state["messages"])
    assert "pending_q" not in at.session_state            # 적재분 소비 완료
    assert not at.chat_input[0].disabled                  # 마무리 rerun 후 해제


def test_processing_run_recovers_input(monkeypatch):
    """pending_q 처리 완주 후 마무리 rerun(v1 :1913) — 입력 재활성·히어로
    미복귀·안내 영속. (처리 중 disabled 잠금 프레임은 라이브 실측으로 검증)"""
    at = _at(monkeypatch)
    at.session_state["pending_q"] = "법인카드 사용 기준이 어떻게 되나요?"
    at.run()
    assert not at.exception
    assert not at.chat_input[0].disabled           # 처리 후 잠금 해제
    assert "무엇을 확인해 드릴까요" not in _all_markdown(at)   # 빈 홈 미복귀
    errs = " ".join(str(e.value) for e in at.error)
    assert "일시적인 오류" in errs                  # 오프라인 — 처리 경로 진입 증명


def test_srms_linkify(monkeypatch):
    """002-B: 비링크 독립 토큰 SRMS → 마크다운 링크 (렌더 직전 치환, 저장
    원문 불변 — 히스토리 엔트리는 그대로), 기링크 입력 이중 치환 0."""
    at = _at(monkeypatch)
    raw1 = "**📋 1차 보고**: SRMS 시스템 즉시 등록 (인지 시점 24시간 內)"
    raw2 = "이미 링크: [SRMS](https://rms.shinsegae.com/) 참조"
    at.session_state["messages"] = [
        {"role": "user", "content": "q1"}, _entry(answer=raw1, cite_n=1),
        {"role": "user", "content": "q2"}, _entry(answer=raw2, cite_n=1),
    ]
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    assert html.count("[SRMS](https://rms.shinsegae.com/)") == 2   # 각 1회
    assert "[[SRMS]" not in html and "]([SRMS]" not in html        # 이중 치환 0
    # 저장 원문 불변
    assert at.session_state["messages"][1]["answer"] == raw1


def test_grade_meta_row(monkeypatch):
    """002-C: HIGH/MEDIUM 어휘 메타 행 + UNVERIFIED 중립·강등 칩 현행 유지."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q1"},
        _entry(grade="HIGH", cite_n=1, ctx_titles=["(재무) 법인카드 관리 지침"],
               elapsed_s=12.3, provider="gemini:g-3.6"),
        {"role": "user", "content": "q2"},
        _entry(grade="MEDIUM", cite_n=1),
        {"role": "user", "content": "q3"},
        _entry(grade="UNVERIFIED", cite_n=1),
        {"role": "user", "content": "q4"},
        _entry(grade="LOW", degraded=True, answer="강등 본문"),
    ]
    at.run()
    assert not at.exception
    html = _all_markdown(at)
    assert "🟢 높은 신뢰도 — 사규 원문 대조 확인" in html
    assert "🟡 보통 신뢰도 — 참고 문서 기반, 원문 대조 권장" in html
    assert "사규 문서 대조 확인 — 세부 조항은 원문 참조" in html   # UNVERIFIED 중립
    assert "신뢰도 강등" in html                                   # LOW 강등 칩
    # HIGH 메타 행 4요소 공존 (카테고리·등급·⏱️·🤖)
    assert "재무" in html and "응답 12.3초" in html and "g-3.6" in html


def test_hero_placeholder_v1_exact(monkeypatch):
    """002-D: 빈 홈 히어로 placeholder = v1 home.py:99 원문 바이트 일치."""
    at = _at(monkeypatch)
    at.run()
    ph = at.text_input(key="hero_q").placeholder
    assert ph == "사규·윤리 관련 무엇이든 물어보세요…"


def test_interrupt_recovery_banner(monkeypatch):
    """중단 복구 간소안: 잔존 inflight + 댕글링 user 턴 → 배너+재실행 버튼,
    클릭 = pending_q 단일 경로 재실행 + 멱등(rerun_done — 버튼 1회 한정)."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "법인카드 사용 기준이 어떻게 되나요?"}]
    at.session_state["_inflight"] = "법인카드 사용 기준이 어떻게 되나요?"
    at.run()
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "직전 답변 생성이 중단되었습니다" in warns
    assert "_inflight" not in at.session_state            # 마커 소거
    btn = next(b for b in at.button if "이 질문 다시 실행" in str(b.label))
    btn.click().run()
    # 재실행 → 처리 경로 진입(오프라인 에러 표면) + 멱등(버튼 소멸·캡션 전환)
    errs = " ".join(str(e.value) for e in at.error)
    assert "일시적인 오류" in errs
    assert not any("이 질문 다시 실행" in str(b.label) for b in at.button)
    caps = " ".join(str(c.value) for c in at.caption)
    assert "다시 실행됨" in caps


def test_no_false_banner_after_completion(monkeypatch):
    """정상 완주 시 inflight 소거 — 허위 배너 없음 (D 조건)."""
    at = _at(monkeypatch)
    at.run()
    at.chat_input[0].set_value("법인카드 사용 기준이 어떻게 되나요?").run()
    assert "_inflight" not in at.session_state
    assert "직전 답변 생성이 중단되었습니다" not in \
        " ".join(str(w.value) for w in at.warning)


def test_stop_suppresses_interrupt_banner(monkeypatch):
    """⏹ 의도된 중지는 중지 안내만 — 중단 배너 중복 없음."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [{"role": "user", "content": "질문"}]
    at.session_state["_stop_requested"] = True
    at.session_state["_inflight"] = "질문"
    at.run()
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "생성이 중지되었습니다" in warns
    assert "직전 답변 생성이 중단되었습니다" not in warns


def test_footer_present(monkeypatch):
    """트랙A ①: v1 app.py:1885-1893 푸터 원문 — 빈 홈·대화 후 공통."""
    at = _at(monkeypatch)
    at.run()
    assert "© 2026 신세계디에프" in _all_markdown(at)
    at2 = _at(monkeypatch)
    at2.session_state["messages"] = [
        {"role": "user", "content": "q"}, _entry(cite_n=1)]
    at2.run()
    assert "© 2026 신세계디에프" in _all_markdown(at2)


def test_history_render_window(monkeypatch):
    """트랙A ②: 최근 30건만 렌더 + 생략 캡션 (v1 :1698-1707 — 성능 가드 겸)."""
    at = _at(monkeypatch)
    msgs = []
    for i in range(17):                       # 34건 → 4건 생략
        msgs.append({"role": "user", "content": f"질문{i}번입니다"})
        msgs.append(_entry(cite_n=1, answer=f"답변{i}번입니다"))
    at.session_state["messages"] = msgs
    at.run()
    assert not at.exception
    caps = " ".join(str(c.value) for c in at.caption)
    assert "이전 4건은 표시 생략" in caps and "최근 30건만 표시" in caps
    html = _all_markdown(at)
    assert "질문0번입니다" not in html         # 윈도우 밖
    assert "질문16번입니다" in html            # 윈도우 안


def test_nomatch_and_transient_notices_render(monkeypatch):
    """트랙A ③·④ 문안 렌더 고정 (분기 자체는 라이브 경로 — 무매칭은 검색
    0건, 일시 장애는 503/429 신호에서 발동. 여기선 영속 엔트리 표출 검증)."""
    at = _at(monkeypatch)
    at.session_state["messages"] = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "notice":
         "💡 질문하신 내용에 직접 해당하는 사규를 찾지 못했습니다. ..."},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "notice_error":
         "⏳ Gemini 모델이 일시적으로 트래픽 폭주 상태입니다 (HTTP 503 / 429)."},
    ]
    at.run()
    assert not at.exception
    warns = " ".join(str(w.value) for w in at.warning)
    assert "직접 해당하는 사규를 찾지 못했습니다" in warns
    errs = " ".join(str(e.value) for e in at.error)
    assert "트래픽 폭주" in errs


def test_sidebar_admin_link(monkeypatch):
    """사이드바 ADMIN 연결 (사용자 의결 — v1 콘솔 링크. 완전 이식은 ADR-8
    심의 후): expander 라벨 v1 정합 + href = v1 admin URL."""
    at = _at(monkeypatch)
    at.run()
    assert any(str(e.label) == "ADMIN" for e in at.expander)
    links = at.get("link_button")
    admin = [l for l in links if "Admin" in str(l.label)]
    assert admin
    assert admin[0].url == "https://df-nexus-ai.streamlit.app/admin"


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


def test_home_pills_v1_parity(monkeypatch):
    """빈 홈 추천 칩 v1 정합 (ui/home.py:9-13·109-126): 정확히 3개, 짧은
    라벨 ↔ 전체 질의 분리, 클릭 시 매핑된 전체 질의가 pending_q 단일 경로로
    제출된다 (오프라인 → 폴백 상수 3쌍)."""
    at = _at(monkeypatch)
    at.run()
    pills = [b for b in at.button if str(b.label) != "↑"]
    assert len(pills) == 3
    labels = {str(b.label) for b in pills}
    assert labels == {"선물 받았어요", "동료 부상", "법인카드"}   # 라벨 = 축약형
    pill = next(b for b in at.button if str(b.label) == "선물 받았어요")
    pill.click().run()
    html = _all_markdown(at)
    # 제출된 것은 라벨이 아닌 매핑된 전체 질의
    assert "거래처에서 선물을 받아도 되나요?" in html
    errs = " ".join(str(e.value) for e in at.error)
    assert "일시적인 오류" in errs                        # 처리 경로 진입 증명


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
