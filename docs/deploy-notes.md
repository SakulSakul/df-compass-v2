# 배포 절차 노트 (v2 배포 문서의 씨앗 — Phase 배포 국면에서 정식화)

## 교훈 1 — secrets 변경은 Reboot 없이는 미반영 (2026-07-22, v1 실측)
v1 `config.py:87` 의 `settings()` 가 `lru_cache` 라 프로세스가 살아있는 동안
secrets 변경(NEXUS_CHAT_MODEL 등)이 반영되지 않는다. **Streamlit Cloud 에서
secrets 를 바꾸면 반드시 Reboot(재기동)까지 해야 적용** — 실측: 재기동 전
전 호출이 구 모델로 기록, 11:48:54 두 번째 "Starting up" 이후 신 모델 확인.

v2 반영 지침: 배포 체크리스트에 "secrets 변경 → Reboot → 로그에서
model= 확인" 3단계를 명시한다. (v2 도 설정 캐시를 쓰게 되면 동일 함정.)

---

## v2 배포 준비 절차 (Phase 2 첫 안건 — 2026-07-22 작성)
**전부 [사용자 액션]. 실행은 사용자 지시 후.** 빌더 전용 프리뷰 전제(배지 유지·URL 비공개).

### 1. Streamlit Cloud 신규 앱 등록
1. share.streamlit.io → New app
2. Repository: `SakulSakul/df-compass-v2` · Branch: `main` · Main file: `app.py`
3. **URL 비공개**: 앱 Settings → Sharing 에서 "Only specific people can view
   this app" 선택, 본인 계정만 뷰어로 — 링크 소지만으로 접근 불가하게.
   (빌더 전용 배지는 코드에 상시 표시되지만, 접근 제어의 본체는 이 설정)

### 2. secrets 목록 (Settings → Secrets)
| 키 | 필수 | 값/비고 |
|---|---|---|
| SUPABASE_URL | ✅ | v1 프로젝트 URL (ADR-8 — 같은 DB) |
| SUPABASE_KEY | ✅ | anon 키 (검색·RPC — SELECT 전용) |
| SUPABASE_SERVICE_KEY | ✅ | service_role (파생 원장 로드 — 읽기 용도로만 사용) |
| GEMINI_API_KEY | ✅ | 합성·리랭크·임베딩 |
| ANTHROPIC_API_KEY | 권장 | Claude fallback + critical LLM 분류기 (없으면 fail-open) |
| NEXUS_CHAT_MODEL | 옵션 | 기본 gemini-3.6-flash (확정값 — 명시 불필요) |
| NEXUS_RERANK_MODEL | 옵션 | 기본 gemini-3.5-flash-lite |
| NEXUS_CLAUDE_MODEL | 옵션 | 기본 claude-opus-4-7 (분류기 fallback) |

### 3. 배포 후 확인 체크리스트 (3층 분리 보고)
- [ ] **소스**: 배포된 커밋 해시 = v2 main 최신 확인
- [ ] **기동**: 로그에 `[registry] ledger built: docs=101` 확인 (원장 로드 성공)
- [ ] **실행 ①**: 비critical 1문항(예: 법인카드) → 섹션 계약 답변 + verify 칩
- [ ] **실행 ②**: critical 1문항(예: 중대재해) → 🚨 배너 + 4단 구조 + 📞 핫라인 박스
- [ ] **실행 ③**: negative 1문항(예: 점심 메뉴) → 무응답+창구 안내 (섹션 강제 없음)
- [ ] URL 비공개 동작 확인 (로그아웃 브라우저에서 접근 차단)
- [ ] ⚠️ **secrets 변경 시 반드시 Reboot** — 교훈 1(lru_cache)과 동일 함정이
  v2 에도 있음: `st.cache_resource` 엔진 초기화가 secrets 를 프로세스 시작
  시점에 읽는다. 변경 → Reboot → 로그로 반영 확인 3단계 준수.
