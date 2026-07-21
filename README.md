# DF COMPASS v2 — 스타터 번들

사용법 (사쿨용):

1. 이 폴더를 새 git 레포로 초기화해서 GitHub에 올린다.
2. 클로드 코드를 이 폴더에서 연다.
3. **"시작해"** 라고만 하면 된다 — CLAUDE.md Part 0 부트스트랩이
   STATUS.md → 현재 Phase 지시서 순으로 알아서 이어간다.
4. `[사용자 액션]` 항목(마이그레이션 실행, 측정 SQL, 표본 감사)이 나오면
   클로드 코드가 정확한 절차를 안내한다. 해주고 결과만 알려주면 된다.
5. Phase가 끝나면 클로드 코드가 판정을 요청한다 — 승인해야 다음 Phase로 넘어간다.

파일 구조:
- `DESIGN.md` — 설계서 v2.1 (단일 기준: council 5인 + 3인 심의 + 스택 검증 반영)
- `CLAUDE.md` — 클로드 코드 행동 규율 + 부트스트랩
- `STATUS.md` — 진행 상태 (클로드 코드가 갱신)
- `docs/phases/phase-0..4.md` — Phase별 작업 지시서
- `tools/gate1-measurement-kit.sql` — v1 Supabase에서 돌리는 측정 SQL 5종
- `tools/cost_calculator.py` — G1 비용 판정 계산기
