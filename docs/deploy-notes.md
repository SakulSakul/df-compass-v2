# 배포 절차 노트 (v2 배포 문서의 씨앗 — Phase 배포 국면에서 정식화)

## 교훈 1 — secrets 변경은 Reboot 없이는 미반영 (2026-07-22, v1 실측)
v1 `config.py:87` 의 `settings()` 가 `lru_cache` 라 프로세스가 살아있는 동안
secrets 변경(NEXUS_CHAT_MODEL 등)이 반영되지 않는다. **Streamlit Cloud 에서
secrets 를 바꾸면 반드시 Reboot(재기동)까지 해야 적용** — 실측: 재기동 전
전 호출이 구 모델로 기록, 11:48:54 두 번째 "Starting up" 이후 신 모델 확인.

v2 반영 지침: 배포 체크리스트에 "secrets 변경 → Reboot → 로그에서
model= 확인" 3단계를 명시한다. (v2 도 설정 캐시를 쓰게 되면 동일 함정.)
