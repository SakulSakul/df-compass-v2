# UI 패리티 매트릭스 (2026-08-06 — 전수 대조, 감리자 인벤토리 기준)

> **최종 마감 라운드 반영** — 검산 지적 2건(피드백 캡션·PROACTIVE DOCK) 이식,
> 사용자 판정 2건(동의서 게이트·비용 가드) 이식, 신규 "이해 확인 + 구체화
> 유도" 표면 구현, 관련 질문 모드 백로그 확정.
> 정정 기록 — "다음 단계 예측" grep 0건 보고는 검색 범위를 render.py·app.py
> 로 한정한 오류였다. 실재 위치 `ui/feedback.py:112-116` (PROACTIVE DOCK).
> 상태: `이식됨` / `대체 설계` / `백로그(사용자 의결)` — **누락 0 · 승인 대기 0**.
> v2 근거는 app.py 커밋 HEAD 기준 (테스트 = tests/test_app_ui.py 어서션).
> 선행 규명 — **피드백 위젯 "실종"**: 현 코드에 존재·비blocked 무조건 렌더
> (app.py `_render_assistant` 피드백 블록), 로컬 스크린샷 렌더 실측. 최초
> 구현 커밋 885d3a0(08-06 07:15) 이전 배포 빌드가 감리 화면이었던 **빌드
> 시차**로 판정 — 회귀·조건부·폴드 아님. 단 v1 전용 플로우 대비 왜소했던
> 것은 사실 → 본 라운드에서 v1 문구 플로우로 정확 이식 + AppTest 고정.

## A. 랜딩·전역
| 항목 | v1 근거 | v2 상태 | v2 근거 |
|---|---|---|---|
| 로고 라인+우측 베타 칩 | app.py:270-278 (nx-brand) / home.py topbar2 | 이식됨 | `.nx-top2` 로고 라인 + "베타·입력 내용 학습 안 함" 칩, AppTest |
| 전폭 베타 배너 (방패+사이드바 안내) | app.py:506-509 | 이식됨 | `.nx-beta-bar` 🛡️ + "자세한 안내는 좌측 사이드바 참조" |
| 히어로 + 레드 물음표 | home.py:66-73 (nx-hero2) | 이식됨 | 54px 타이포+`.q` 레드 물음표 (computed 54px 기계 확인), 오타 회귀 테스트 |
| 중앙 대형 입력 + 원형 레드 전송 | home.py:76-110 (hero_ask_input) | 이식됨 | `hero_q`/`hero_go` (원형 50%·rgb(200,16,46) 기계 확인), 하단 입력 병존 |
| 예시 칩 (pill) | home.py 예시 칩 + styles 칩 규칙 | 이식됨 | pill 999px 6종 (상황형 3 추가) |
| 사이드바 4요소 (브랜드·안내·핫라인·디스클레이머) | app.py:268-315 | 이식됨 | `_sidebar` — v1 문안 + 질의 범위 추가 |
| 시간대·요일 인사 (empty-state) | personality.py:96-121 (fallback_greeting) | 이식됨 | `_greeting_line()` 버킷 로직 이식 → 히어로 서브 |
| 베타 참가 동의서 게이트 | app.py:1411-1533 (consent_version) | 이식됨 (사용자 판정) | `_consent_gate()` — v1 문안·검증 regex·prod 비활성 규칙 동일. 차이: 쿠키 30일 영속 미이식(CookieManager rerun 인터럽트 사고 이력 — 세션 단위 동의), DB 기록은 ADR-8 로 stderr 기록 대체(심의 후 영속화). 동의서 본문의 데이터 흐름 서술은 v2 실태(질의 로그 무저장)로 정정. AppTest |
| 베타 비용 가드 (일일 한도 안내) | app.py:515-532·608-615 (daily_query_limit) | 이식됨 (사용자 판정) | `_check_rate_limit()` — KST 자정 리셋·세션 카운터·v1 한도값(NEXUS_DAILY_QUERY_LIMIT=100)·경고 문구 원문. 안내는 notice 엔트리로 히스토리 영속. AppTest |
| 푸터 고지 | app.py 하단 고지 | 이식됨 | 사이드바 디스클레이머로 통합 (v1 문안 동일) |

## B. 답변 상단
| 항목 | v1 근거 | v2 상태 | v2 근거 |
|---|---|---|---|
| 검토 과정 expander + 캡션 | app.py:1157 ("AI가 답변을 생성한 검토 단계입니다…") | 이식됨 | 🧠 expander + 동일 캡션 원문, AppTest |
| 판정 카드 (stance pill·세리프 인용·출처) | cards.py:97-148 (_build_verdict_card_html) | 이식됨 | `_verdict_card_data` 결정론 파싱 + v1 색조(`_STANCE_TONE`) — v1은 LLM verdict, v2는 핵심 결론 파싱(엔진 무접촉 대체) |
| 신뢰도 칩 | cards.py:121-122 (conf_label) | 이식됨 | conf 4등급 사용자 라벨 (심의 3항) — HIGH/MEDIUM/UNVERIFIED + LOW=강등 칩 |
| 신뢰도 부족 게이트 (❌) | chatbot.py 게이트①② (SAFE_NO_CONTEXT 등) | **대체 설계** | v2 는 §5 verify 체계가 대체: block(비실재 인용 차단)·degrade(강등 칩)·UNVERIFIED 라벨. v1 게이트류(검색 부실 deflect)는 v2 보장 계층+negative 무응답 표명이 담당 |

## C. 본문
| 항목 | v1 근거 | v2 상태 | v2 근거 |
|---|---|---|---|
| 타이핑 효과 | ask_stream (실 스트리밍) | **대체 설계 (의결 반영)** | 검증 후 재생(`_typewriter`+st.write_stream) — 실 스트리밍은 절단 게이트·verify 전제 충돌로 금지(08-06 사용자 확정), 안전 표면은 재생 전 즉시 표시 |
| 4단 구조 (critical) | critical_mode enforce_structure | 이식됨 (v1port byte-identical) | critical 배너+4단+핫라인 — 발효 감리 실측 |

## D. 답변 하단
| 항목 | v1 근거 | v2 상태 | v2 근거 |
|---|---|---|---|
| 카테고리 뱃지 (💳 재무 등) | render.py:142-165 | 이식됨 | `_category_of` 접두어 최빈값 + `_CAT_ICON` 10종, AppTest |
| ⏱·🤖 표기 | app.py:709-713 (elapsed) + 모델 표기 | 이식됨 | "⏱️ 응답 N초 · 🤖 모델" 메타 라인 |
| 참고 사규 expander | render.py:296-312 (_render_contexts) | 이식됨 | ctx_refs 발췌(escape — v1 XSS 교훈 승계) expander |
| 💡 이런 질문도 해볼 수 있어요 | render.py:207 | 이식됨 | 동일 문구 + grounded 제안(auto_query_examples SELECT) |
| 다음 단계 예측 (PROACTIVE DOCK) | ui/feedback.py:112-140 (grep 누락 정정) + core/nexus_button_branch.py | 이식됨 (검산 지적②) | 라벨 div 원문 + 분기 주 액션(신고/클린신고/인사 문의 — classify_button 다중 신호 축약 이식, confidence 는 grade/degrade 로 대응) + 패널 3종(ui/panels.py 축약) + 🔄 다시 답변(1회 한정 — v2 단일 턴이라 동일 질문 재실행, prev_answer 전달은 엔진 접촉이라 미이식). AppTest |
| personality 클로징 (시간·요일) | personality.py:31-50 (closing_remark 풀) | 이식됨 | `_closing_line` — NORMAL/CRITICAL 풀 원문, 세션 결정론 pick |
| 👍👎 피드백 전체 플로우 | feedback.py:306·313·314 | 이식됨 (플로우 문구 + 캡션) | "이 답변이 정확하고 도움이 되셨나요?" + 캡션 "베타 단계입니다…"(검산 지적①) + 👍👎 + "✅ 피드백 감사합니다." — **DB 영속화만 ADR-8 심의 대기(세션+stderr 기록)**, AppTest |
| 🔗 관련 추가 질문 모드 | app.py:618-631 (prev_turn) | **백로그 확정 (사용자 의결 4항)** | 엔진형(prev_turn 전달)은 엔진 접촉 — 신규 "이해 확인 + 구체화 유도" 표면의 실사용 결과가 그 설계의 입력이 된다 |
| 이해 확인 + 구체화 유도 표면 | (신규 — 사용자 설계, v1 prompts.py:296 규칙3 어근) | 이식됨 (신규 구현) | `_is_fragment_followup` 파편·지시어 감지(직전 턴 존재 전제, 보수적) → 검색 미실행, 재진술 + 단일 턴 안내 + 직전 답변 followups(실재 예시) 자동 제출 칩 ≤3. no-op 폴백(직전 턴 부재 시 현행 동작) AppTest 고정. 일반 답변 하단엔 "보다 구체적인 답변을 위해…" 유도 캡션 |

## E. 상태별
| 상태 | v1 근거 | v2 상태 | v2 근거 |
|---|---|---|---|
| critical | 배너+4단+핫라인 | 이식됨 (불변 조건) | AppTest 3불변 + 발효 감리 실측 |
| OOS(범위 밖) | oos 카드·무응답 | 이식됨 (대응 체계) | 무응답 표명 + '참고 인용' 구획 + UNVERIFIED 라벨 + 담당 창구 안내 (합성 계약) |
| 에러 | 친화 안내 | 이식됨 (신규) | `_ask` 예외 → st.error 친화 문구 + stderr 로그 (스택 비노출) |
| 동의 게이트(베타 진입) | app.py:1464-1494 동의 화면 | 이식됨 | 히어로형 동의 화면 + 성명/사번/체크박스 + 검증 — AppTest·스크린샷(state_consent) |
| 파편 후속 질문 | (v1 은 멀티턴이 처리) | 이식됨 (유도 표면) | 검색 미실행 + 이해 확인 + 구체화 칩 — AppTest·스크린샷(state_coach) |
| 한도 초과 | app.py:610-614 경고 | 이식됨 | st.warning 원문 + notice 엔트리 영속 — AppTest |
| 로딩 | 단계 progress+elapsed 카운터 | **부분 대체** | 스피너("사규를 확인하고 답변을 작성하는 중…") — v1 단계별 카운터는 파이프라인 단계 노출(개발 표시 제거 원칙)과 상충해 스피너+완료 후 검토 과정 expander 로 대체 |
| 스트리밍 중 | 실 스트리밍 표면 | 대체 설계 | C 항 타이핑 재생과 동일 (의결) |

## 잔여 사항 (승인 대기 0 — 전건 의결 완료)
1. ~~베타 참가 동의서 게이트~~ → **이식 완료** (사용자 판정)
2. ~~베타 비용 가드~~ → **이식 완료** (사용자 판정, v1 한도값)
3. **🔗 관련 추가 질문 모드(엔진형)** → **백로그 확정** (사용자 의결 4항 —
   유도 표면 실사용 결과가 설계 입력)
+ 피드백·동의 **DB 영속화**는 ADR-8 별도 심의 기이관 (표면·플로우는 이식 완료)
+ ~~다음 단계 예측 근거 미발견~~ → 감리자 회신(`ui/feedback.py:112-116`)으로
  **이식 완료** — grep 범위 한정 오류 정정 기록 상단 참조
