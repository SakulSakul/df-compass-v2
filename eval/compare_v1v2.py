"""v1·v2 비교 러너 (지시서 전체) — golden 52 를 양 시스템 동일 조건 실행.

- v1: 로컬 사이드카 (eval/v1_sidecar.py, ★배포 앱 호출 금지·쓰기 차단 주입)
- v2: 동결 구성 그대로 (pipeline_run.py 미러 — v4-ctx + keyword leg +
  rerank 3.5-flash-lite/minimal + neighbors±2 + 합성 3.6 + §5 verify 기록)
- 채점: §4 매트릭스 — 비교 판정은 양쪽 공통 지표만, v2 전용 지표는 병기
- §2 스모크 게이트: 본 러닝은 스모크(고정 g09/g47) 전부 통과 후에만 진행
- §5 변형 트랙: eval/variants.yaml (커밋본) 존재 시 실행, 별도 섹션 기록
- §6 blindspot: registry 결정론 태그 + 전체/제외 이중 집계

사용:  python eval/compare_v1v2.py --smoke        # 게이트만
       python eval/compare_v1v2.py               # 게이트 → 본 러닝(+변형)
       python eval/compare_v1v2.py --no-variants
env: SUPABASE_URL, SUPABASE_KEY(anon), GEMINI_API_KEY (v1·v2 공용 anon —
     운영 v1 과 동일 키 클래스, ADR-8 SELECT/RPC 전용)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import os
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
# ⚠️ v2 import 를 전부 먼저 — v1 레포에도 최상위 eval/ 이 있어 사이드카는
# sys.path 끝에 append 하지만, import 순서로도 이중 방어한다.
from supabase import create_client  # noqa: E402
from compass_engine.intake import run_intake  # noqa: E402
from compass_engine.registry import load_ledger  # noqa: E402
from compass_engine.reranker import GeminiReranker  # noqa: E402
from compass_engine.synthesis import synthesize  # noqa: E402
from compass_engine.v1_retriever import V1RpcRetriever, gemini_embed_fn  # noqa: E402
from compass_engine.verify import verify_answer  # noqa: E402
from eval.compare_matrix import (  # noqa: E402
    blindspot_titles, matrix_report, suspicious_rpc_names, tag_blindspot)
from eval.golden_ab import _score  # noqa: E402  (채점 로직 단일 소스)
from eval.runner import RESULTS_DIR, load_fixtures  # noqa: E402
from eval.v1_sidecar import (  # noqa: E402
    GuardedSupabase, load_v1_chatbot, run_env_snapshot, run_v1)

SMOKE_IDS = ("g09", "g47")  # §2 고정 표본 — standard 1 + negative 1
VARIANTS_PATH = _ROOT / "eval" / "variants.yaml"
V2_CONFIG = ("v4-ctx RPC + keyword leg + rerank(3.5-flash-lite/minimal, "
             "pool15→top3) + neighbors±2 + synthesis(3.6) + §5 verify(기록)")


def _attempt(fn, qid: str, label: str):
    """pipeline_run.py 재시도 미러 — 1회 재시도, 소진 시 실패 기록."""
    for attempt in (1, 2):
        try:
            return fn(), None
        except Exception as ex:
            print(f"[compare] {qid} {label} attempt{attempt} FAILED: "
                  f"{type(ex).__name__}: {ex}", file=sys.stderr, flush=True)
            if attempt == 2:
                return None, f"{type(ex).__name__}: {ex}"
            time.sleep(5)


class Harness:
    def __init__(self) -> None:
        url = os.environ["SUPABASE_URL"]
        anon = os.environ.get("SUPABASE_ANON_KEY") or os.environ["SUPABASE_KEY"]
        self.sb_v2 = create_client(url, anon)
        self.ledger = load_ledger(create_client(url, anon))
        # wave 2 합성 계약 — 앵커 사전 (플래그 off 시 None = 어블레이션)
        from compass_engine.anchors import build_anchor_map
        self.anchor_map = (build_anchor_map(self.ledger)
                           if os.environ.get("NEXUS_ENABLE_CITATION_CONTRACT",
                                             "true").lower() == "true" else None)
        self.rr = GeminiReranker()
        # wave 3 보장 계층 — 플래그 off 시 종전 동결 구성 (어블레이션)
        if os.environ.get("NEXUS_ENABLE_GUARANTEE_LAYER", "true").lower() == "true":
            from compass_engine.doc_router import DocRouter
            self.retr = V1RpcRetriever(
                self.sb_v2, gemini_embed_fn(), top_k=5,
                rpc_name="nexus_hybrid_search_v4_ctx",
                expand_neighbors=True, neighbor_radius=1,
                reranker=self.rr, rerank_pool=25,
                router=DocRouter(self.sb_v2), reserved_seats=2,
                proxy_quota=1, chunk_cap=8)
        else:
            self.retr = V1RpcRetriever(self.sb_v2, gemini_embed_fn(), top_k=3,
                                       rpc_name="nexus_hybrid_search_v4_ctx",
                                       expand_neighbors=True, reranker=self.rr)
        # v1 사이드카 — 쓰기 차단 클라이언트 주입 (운영과 동일 anon 키 클래스)
        self.v1_chatbot = load_v1_chatbot()
        self.sb_v1 = GuardedSupabase(create_client(url, anon))
        self.bs_titles = blindspot_titles(self.ledger)

    def run_v2_side(self, question: str) -> dict:
        t0 = time.perf_counter()
        res = self.retr.retrieve(
            {"masked_text": question, "is_critical": False,
             "critical_matches": [], "oos": False, "faq_hit_id": None,
             "ambiguity": None},
            {"tracks": ["rule"], "intent": "compare_v1v2"})
        syn = synthesize(question, res["chunks"], anchor_map=self.anchor_map)
        total_s = time.perf_counter() - t0
        verdict = verify_answer(syn.answer_md, self.ledger,
                                synthesis_integrity_ok=syn.integrity_ok)
        # critical 발동 기록(§3, 기록 지표) — 채점 경로(동결 구성) 밖에서
        # intake 만 별도 실행. 결과는 기록만 하고 파이프라인에 주입하지 않는다.
        intake = run_intake(self.sb_v2, question)
        return {
            "answer": syn.answer_md,
            "elapsed_total_s": round(total_s, 3),
            "synth_ms": syn.elapsed_ms,
            # wave 1 계측 (재검증 성립 조건): 단계 타이머·최종 청크 수·
            # 합성 입력 크기·라우터 히트
            "timings": res.get("timings", {}),
            "n_chunks": len(res["chunks"]),
            "input_chars": syn.input_chars,
            "integrity_ok": syn.integrity_ok,
            "synth_retries": syn.retries,
            "router_hit": res.get("router_hit"),
            "provider": syn.provider,
            "used_fallback": syn.used_fallback,
            "section_contract_ok": syn.section_contract_ok,
            "verify": {"action": verdict["action"],
                       "grade": verdict["grade"],     # wave 2: 서수 4등급
                       "ok": sum(1 for c in verdict["citations"]
                                 if c["verdict"] == "ok"),
                       "n": len(verdict["citations"])},
            "is_critical": intake["is_critical"],
            "critical_kind": intake.get("critical_kind"),
            "context_docs": sorted({c.get("doc_title") or c.get("breadcrumb", "")
                                    .split(" › ")[0]
                                    for c in res["chunks"]}),
        }

    def run_v1_side(self, question: str) -> dict:
        return run_v1(self.v1_chatbot, self.sb_v1, question)

    def run_question(self, entry: dict, question: str | None = None) -> dict:
        q = question or entry["question"]
        rec: dict = {"id": entry["id"], "category": entry.get("category"),
                     "question": q,
                     "blindspot": tag_blindspot(entry, self.bs_titles)}
        for label, fn in (("v1", lambda: self.run_v1_side(q)),
                          ("v2", lambda: self.run_v2_side(q))):
            side, err = _attempt(fn, rec["id"], label)
            if side is None:
                rec[label] = {"failed": True, "error": err}
            else:
                side["score"] = _score(side["answer"], entry, self.ledger)
                rec[label] = side
        return rec


# ── §2 스모크 게이트 ──────────────────────────────────────────────


def run_smoke(h: Harness, entries: list[dict]) -> bool:
    by_id = {e["id"]: e for e in entries}
    checks: list[tuple[str, bool, str]] = []
    for sid in SMOKE_IDS:
        rec = h.run_question(by_id[sid])
        for system in ("v1", "v2"):
            side = rec[system]
            ok_exc = not side.get("failed")
            checks.append((f"{sid}/{system} ① 예외 0", ok_exc,
                           side.get("error", "")))
            ans = (side.get("answer") or "").strip()
            checks.append((f"{sid}/{system} ② 답변 비어있지 않음", bool(ans),
                           f"len={len(ans)}"))
            sc = side.get("score")
            checks.append((f"{sid}/{system} ③ 채점기 파싱",
                           isinstance(sc, dict) and "expected_total" in sc,
                           str({k: sc.get(k) for k in ("expected_hit",
                                "expected_total", "has_fabrication")}
                               if isinstance(sc, dict) else sc)))
        mp = rec["v1"].get("module_path", "")
        checks.append((f"{sid} ④ v1 실코드 경로", "nexus_ai" in mp, mp))
    guard = h.sb_v1.guard_log.summary()
    # ⑤ 실검사 (감리 지적 2 보완): table 쓰기는 프록시가 구조 차단하므로,
    # 우회 가능 경로인 RPC 의 이름을 쓰기성 패턴과 대조해 판정한다.
    # (from_/postgrest/storage 는 v1 ask() 경로 미사용 — grep 전수 확인 증거는
    # 완료 보고 첨부. admin 페이지 1곳뿐이며 사이드카는 로드하지 않는다.)
    sus = suspicious_rpc_names(guard["rpc_calls"])
    checks.append(("⑤ v1 DB 쓰기 0 (가드+RPC 이름 대조)", not sus,
                   f"blocked={guard['blocked_write_count']} "
                   f"rpc={list(guard['rpc_calls'])} 쓰기성_의심={sus}"))
    print("\n──── §2 스모크 게이트 ────")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
        all_ok = all_ok and ok
    print(f"──── 스모크 {'전부 통과' if all_ok else '실패 — 본 러닝 금지'} ────\n")
    return all_ok


# ── 변형 트랙 (§5) ────────────────────────────────────────────────


def load_variants(entries: list[dict]) -> list[tuple[dict, dict]]:
    """커밋된 variants.yaml → [(변형행, base entry)] (재생성 없음)."""
    if not VARIANTS_PATH.exists():
        return []
    import yaml
    rows = yaml.safe_load(VARIANTS_PATH.read_text(encoding="utf-8")) or []
    by_id = {e["id"]: e for e in entries}
    out = []
    for r in rows:
        base = by_id.get(r.get("base_id"))
        if base and base.get("category") not in ("critical", "negative"):
            out.append((r, base))
    return out


# ── main ─────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="게이트만 실행")
    ap.add_argument("--no-variants", action="store_true")
    args = ap.parse_args()

    h = Harness()
    entries = load_fixtures(_ROOT / "eval" / "golden.yaml")

    if not run_smoke(h, entries):        # §2: 통과 전 본 러닝 금지
        return 1
    if args.smoke:
        return 0

    records = []
    for i, e in enumerate(entries, 1):
        records.append(h.run_question(e))
        print(f"… golden {i}/{len(entries)}", flush=True)

    variant_records = []
    if not args.no_variants:
        pairs = load_variants(entries)
        for i, (v, base) in enumerate(pairs, 1):
            rec = h.run_question({**base, "id": v["id"]},
                                 question=v["question"])
            rec["base_id"] = v["base_id"]
            variant_records.append(rec)
            print(f"… variant {i}/{len(pairs)}", flush=True)

    report = matrix_report(records)
    v_report = matrix_report(variant_records) if variant_records else None
    guard = h.sb_v1.guard_log.summary()
    out = {
        "timestamp": datetime.now().isoformat(),
        "purpose": "v1·v2 non-inferiority 증거 (컷오버 풀 심의 입력)",
        "v1_config": run_env_snapshot(),
        "v1_module_path": str(h.v1_chatbot.__file__),
        "v2_config": V2_CONFIG,
        "v1_write_guard": guard,
        "limitations": [
            "로컬 실행 지연은 배포 환경 절대값이 아님 — v1↔v2 상대 비교 전용",
            "v1 합성 단독 지연은 몽키패치 금지로 미계측 — 총 지연만 비교",
            "운영 Streamlit secrets 의 ENABLE_* flag 실값은 로컬 확인 불가 — "
            "v1 코드 기본값(false) 으로 실행, v1_config.env_vars 참조",
            "v1 은 critical 시 enforce_structure(핫라인) 포함 답변, v2 채점 "
            "경로는 동결 구성(합성 원문) — 채점은 동일 스코어러로 텍스트 대조",
            "지연 계측 경계 비대칭: v1 총지연은 ask() 전체(내부 게이트·로깅 "
            "시도 포함), v2 총지연은 retrieve+synthesize (intake·verify 는 "
            "채점 밖 별도 실행이라 미포함) — 상대 비교 시 감안 (감리 지적 3)",
        ],
        "records": records,
        "matrix": report,
        "variant_track": {"records": variant_records, "matrix": v_report},
    }
    path = RESULTS_DIR / (
        f"compare_v1v2_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    print("\n════ v1·v2 비교 · golden 52 (§4 매트릭스) ════")
    for scope in ("all", "excl_blindspot"):
        tag = "전체" if scope == "all" else "blindspot 제외"
        print(f"[{tag}]  (blindspot {len(report['blindspot_ids'])}문항: "
              f"{report['blindspot_ids']})" if scope != "all"
              else f"[{tag}]")
        for system in ("v1", "v2"):
            a = report[system][scope]
            rc = f"{a['exp_hit']}/{a['exp_total']}"
            rr_ = f"({a['recall']:.1%})" if a["recall"] is not None else ""
            print(f"  {system}: 재현율 {rc} {rr_} | 위조답변 {a['fab_answers']}"
                  f"/{a['answers']} | neg {a['neg_pass']}/{a['neg_total']} | "
                  f"총지연 p50 {a['latency_p50_s']}s p95 {a['latency_p95_s']}s"
                  f" | 실패 {a['failed']}")
    if v_report:
        a1, a2 = v_report["v1"]["all"], v_report["v2"]["all"]
        print(f"[변형 트랙 — 참고 지표, 판정 미산입] v1 재현율 "
              f"{a1['exp_hit']}/{a1['exp_total']} ↔ v2 {a2['exp_hit']}/"
              f"{a2['exp_total']} | 위조 {a1['fab_answers']}↔{a2['fab_answers']}")
    print(f"guard: blocked_writes={guard['blocked_write_count']} "
          f"(실쓰기 0 — 전부 차단)")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
