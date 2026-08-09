"""트랙 C — v1·v2 자동 E2E 비교 하니스 (감리자 지시서 2/2).

v1(/home/user/nexus_ai)·v2(/workspace/df-compass-v2)를 로컬 streamlit 으로
각각 기동해(키는 로컬 env — 값 출력 금지) 동일 시나리오를 돌리고, 상태별
DOM 체크리스트를 양쪽 동일 기준으로 판정한다. DIFF 는 의도 여부 판단 없이
원시 기록만 남긴다 (판정은 감리자 독립 재검산).

시나리오: 빈 홈 → 질문 제출 → 처리 중(2s 간격 샘플) → 답변 완료 → 피드백.
NEXUS_ENV=prod-e2e 로 기동 — 양쪽 모두 동의 게이트 비활성(v1 규칙 동일)이라
게이트 통과 절차 없이 본 표면만 비교한다. v1 무수정·엔진 무접촉.
(v1 query_logs INSERT 는 v1 앱 자체 동작 — 통상 사용 범위로 허용.)

실행: python tools/e2e_compare/run_compare.py
산출: eval/results/e2e_compare_<ts>.json + eval/results/e2e_shots_<ts>/
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

V1_DIR = "/home/user/nexus_ai"
V2_DIR = "/workspace/df-compass-v2"
V1_PORT, V2_PORT = 8601, 8602
TS = time.strftime("%Y%m%d_%H%M%S")
OUT_DIR = Path(V2_DIR) / "eval" / "results"
SHOT_DIR = OUT_DIR / f"e2e_shots_{TS}"

QUESTIONS = [
    ("fair_trade", "하도급 협력사 선정 기준이 어떻게 되나요?"),
    ("finance", "법인카드 사용 기준이 어떻게 되나요?"),
    ("hr", "연차 휴가는 어떻게 신청하나요?"),
    ("safety", "사무실 공기질 관리 기준이 궁금합니다."),
    ("csr", "협력사에서 선물을 받았는데 어떻게 해야 하나요?"),
    ("nomatch", "오늘 점심 메뉴 추천해줘"),
]

ANSWER_MARKERS = ("이 답변이 정확하고", "찾지 못했습니다", "일시적인 오류",
                  "트래픽 폭주", "차단되었습니다")

# 부분 재실행: python run_compare.py fair_trade,hr,nomatch
if len(sys.argv) > 1:
    _sel = set(sys.argv[1].split(","))
    QUESTIONS = [q for q in QUESTIONS if q[0] in _sel]


def _launch(app_dir: str, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update({
        "NEXUS_ENV": "prod-e2e",
        # v2 별칭 매핑 (값은 기존 env 재사용 — 출력 금지)
        "SUPABASE_ANON_KEY": os.environ.get("SUPABASE_KEY", ""),
        "SUPABASE_SERVICE_KEY": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
    })
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(port), "--server.headless", "true"],
        cwd=app_dir, env=env,
        stdout=open(SHOT_DIR / f"server_{port}.log", "w"),
        stderr=subprocess.STDOUT, start_new_session=True)


async def _checks(pg) -> dict:
    """상태 스냅샷 — 양쪽 동일 기준 DOM 체크리스트."""
    return await pg.evaluate("""
      () => {
        const vis = (el) => { const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0
                 && getComputedStyle(el).display !== 'none'
                 && getComputedStyle(el).visibility !== 'hidden'; };
        const q = (s) => [...document.querySelectorAll(s)];
        const bodyTxt = document.body.innerText;
        // 가시 입력창 수 (chat textarea + text input — 사이드바 selectbox 제외)
        const inputs = q('[data-testid="stChatInput"] textarea, [data-testid="stMainBlockContainer"] input[type="text"]')
                        .filter(vis).length;
        const chips = q('[class*="st-key-hpill_"] button').filter(vis).length;
        const stop = q('button').filter(b => vis(b) && b.innerText.includes('생성 중지')).length > 0;
        const dockBtns = q('button').filter(b => vis(b) &&
          /(신고 방법 안내|클린신고 안내|인사교육팀 문의|경리팀)/.test(b.innerText))
          .map(b => b.innerText.trim());
        const fb = q('button').filter(b => vis(b) &&
          /(도움됐어요|아쉬워요)/.test(b.innerText)).length > 0;
        // 다크텍스트 소실: 답변 영역 p/li 중 밝은 배경 위 근백색 텍스트
        let ghost = 0;
        q('[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li')
          .slice(0, 60).forEach(el => {
            const c = getComputedStyle(el).color.match(/\\d+/g);
            if (c && (+c[0] + +c[1] + +c[2]) / 3 > 220) ghost += 1; });
        return {
          visible_inputs: inputs,
          home_chips: chips,
          stop_btn: stop,
          dock_labels: dockBtns,
          dock_present: bodyTxt.includes('다음 단계 예측'),
          feedback_btns: fb,
          footer: bodyTxt.includes('© 2026 신세계디에프'),
          ghost_text_nodes: ghost,
        };
      }""")


async def _timer_present(pg) -> bool:
    for f in pg.frames:
        try:
            if await f.locator("#dfc-elapsed").count():
                return True
        except Exception:
            pass
    return False


async def _run_app(pw, name: str, port: int) -> dict:
    from playwright.async_api import TimeoutError as PWTimeout
    b = await pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    out: dict = {"app": name, "questions": {}}
    for qkey, qtext in QUESTIONS:
        pg = await b.new_page(viewport={"width": 1440, "height": 1000})
        rec: dict = {}
        try:
            await pg.goto(f"http://localhost:{port}", wait_until="networkidle",
                          timeout=90000)
            await pg.wait_for_timeout(6000)
            # ① 빈 홈
            rec["home"] = await _checks(pg)
            await pg.screenshot(path=str(SHOT_DIR / f"{name}_{qkey}_home.png"))
            # ② 제출 — 양쪽 공통으로 하단 chat_input 은 빈 홈에서 숨김이므로
            #    중앙 히어로 입력 사용 (v1 hero_ask_input / v2 hero_q)
            hero = pg.locator('[data-testid="stMainBlockContainer"] input[type="text"]').first
            await hero.fill(qtext)
            await hero.press("Enter")
            # ③ 처리 중 — 2s 간격 샘플 (최대 3회, 완료 감지 시 중단)
            samples = []
            for si in range(3):
                await pg.wait_for_timeout(2000)
                body = await pg.inner_text("body")
                if any(m in body for m in ANSWER_MARKERS):
                    break
                s = await _checks(pg)
                s["timer"] = await _timer_present(pg)
                samples.append(s)
                await pg.screenshot(
                    path=str(SHOT_DIR / f"{name}_{qkey}_proc{si}.png"))
            rec["processing_samples"] = samples
            # ④ 답변 완료 대기 (최대 150s)
            done = False
            for _ in range(30):
                await pg.wait_for_timeout(5000)
                body = await pg.inner_text("body")
                if any(m in body for m in ANSWER_MARKERS):
                    done = True
                    break
            rec["answered"] = done
            # 답변 하단 위젯(피드백·dock) 안착 대기 — v2 는 마무리 rerun 뒤
            # 렌더되므로 직전 프레임 스냅샷의 타이밍 아티팩트를 제거한다
            for _ in range(8):
                settled = await pg.evaluate(
                    "() => [...document.querySelectorAll('button')]"
                    ".some(b => /도움됐어요|아쉬워요/.test(b.innerText))")
                if settled:
                    break
                await pg.wait_for_timeout(1500)
            await pg.wait_for_timeout(1500)
            fin = await _checks(pg)
            fin["timer_after"] = await _timer_present(pg)
            rec["answer"] = fin
            await pg.screenshot(
                path=str(SHOT_DIR / f"{name}_{qkey}_answer.png"), full_page=True)
        except (PWTimeout, Exception) as e:              # noqa: BLE001
            rec["error"] = f"{type(e).__name__}"
        out["questions"][qkey] = rec
        await pg.close()
    await b.close()
    return out


def _diff(v1: dict, v2: dict) -> dict:
    """문항×상태×항목 PASS/DIFF — 원시 기록 (의도 판단 없음)."""
    table: dict = {}
    for qkey, _ in QUESTIONS:
        r1 = v1["questions"].get(qkey, {})
        r2 = v2["questions"].get(qkey, {})
        row: dict = {}
        for state in ("home", "answer"):
            a, b2 = r1.get(state) or {}, r2.get(state) or {}
            keys = sorted(set(a) | set(b2))
            row[state] = {k: ("PASS" if a.get(k) == b2.get(k)
                              else {"v1": a.get(k), "v2": b2.get(k)})
                          for k in keys}
        # 처리 중: 타이머·중지 존재 여부만 대표 비교 (샘플 타이밍은 원시 보존)
        s1 = r1.get("processing_samples") or []
        s2 = r2.get("processing_samples") or []
        row["processing"] = {
            "timer_any": ("PASS" if any(s.get("timer") for s in s1)
                          == any(s.get("timer") for s in s2)
                          else {"v1": [s.get("timer") for s in s1],
                                "v2": [s.get("timer") for s in s2]}),
            "stop_any": ("PASS" if any(s.get("stop_btn") for s in s1)
                         == any(s.get("stop_btn") for s in s2)
                         else {"v1": [s.get("stop_btn") for s in s1],
                               "v2": [s.get("stop_btn") for s in s2]}),
        }
        row["answered"] = ("PASS" if r1.get("answered") == r2.get("answered")
                           else {"v1": r1.get("answered"), "v2": r2.get("answered")})
        table[qkey] = row
    return table


async def main() -> None:
    from playwright.async_api import async_playwright
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    p1 = _launch(V1_DIR, V1_PORT)
    p2 = _launch(V2_DIR, V2_PORT)
    try:
        time.sleep(12)
        async with async_playwright() as pw:
            v1 = await _run_app(pw, "v1", V1_PORT)
            v2 = await _run_app(pw, "v2", V2_PORT)
        report = {
            "ts": TS,
            "note": "DIFF 는 원시 기록 — 의도/결함 판정은 감리자 재검산",
            "diff_table": _diff(v1, v2),
            "raw": {"v1": v1, "v2": v2},
        }
        out_path = OUT_DIR / f"e2e_compare_{TS}.json"
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(f"JSON: {out_path}")
        print(f"SHOTS: {SHOT_DIR}")
    finally:
        for p in (p1, p2):
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
