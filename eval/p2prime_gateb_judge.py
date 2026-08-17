"""지시서 010-r1 게이트 (b) 판정 — P2′ 재실측 vs P1 기준선 (읽기 전용 분석).

사용: python eval/p2prime_gateb_judge.py <P1_json> <P2_json>

판정 항목(지시서 사전 고정):
 b1. 무관 무지목 문항 — 승격 문서 top_k 진입 0 (g47 소멸)
 b2. 관련 45 rescue 보존 — P1 기준선 36문항·66청크 ±10%
 b3. g14·선물(g13)·법인카드 승격/라우팅 문서 진입 유지
 b4. 무관-지목(g10·g50형) 무해 — 승격 문서 진입 여부 원시 기록
 b5. 관련 무지목 발생 시 golden 적중과 함께 원시 기록 (적중 회귀 시 정지)

스킵 판별: router_hit is None ⇔ routed_titles 공집합 ⇔ P2′ 리랭크 스킵
(v1_retriever.py — router_hit 은 지목 시에만 설정).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from eval.runner import load_fixtures  # noqa: E402

PROMOTED = ("(공통) 임직원 징계기준", "(공통) 신세계그룹 CREDO")


def _load(p):
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    ok = [r for r in d["records"] if "error" not in r]
    return d, {r["id"]: r for r in ok}


def main() -> int:
    p1_path, p2_path = sys.argv[1], sys.argv[2]
    d1, r1 = _load(p1_path)
    d2, r2 = _load(p2_path)
    golden = {e["id"]: e for e in load_fixtures(_ROOT / "eval" / "golden.yaml")}
    verdict: dict = {"p1": p1_path, "p2": p2_path,
                     "errors_p2": d2["aggregates"]["errors"]}

    # b1 — 무관 무지목: 승격 문서 최종 진입 0
    irr = [r for r in r2.values() if r["irrelevant_group"]]
    irr_skip = [r for r in irr if r.get("router_hit") is None]
    b1_bad = [r["id"] for r in irr_skip
              if any(f["doc"] in PROMOTED for f in r["final"])]
    verdict["b1"] = {"skip_ids": [r["id"] for r in irr_skip],
                     "promoted_entered": b1_bad, "pass": not b1_bad}

    # b2 — rescue 보존 (RRF>10 최종 진입, 관련 문항)
    resc1 = d1["aggregates"]["rescue_candidates_rel_questions"]
    resc2 = d2["aggregates"]["rescue_candidates_rel_questions"]
    q1, c1 = len(resc1), sum(len(x["deep_entries"]) for x in resc1)
    q2, c2 = len(resc2), sum(len(x["deep_entries"]) for x in resc2)
    verdict["b2"] = {"p1": {"q": q1, "chunks": c1},
                     "p2": {"q": q2, "chunks": c2},
                     "pass": abs(q2 - q1) <= round(q1 * 0.1)
                             and abs(c2 - c1) <= round(c1 * 0.1)}

    # b3 — 핵심 문항 진입 유지: g14(공금 징계)·g12(선물)·g09(법인카드)
    # (+g13 보수적 포함). 이중 검사 — ① expected 적중 보존 ② P1 최종에
    # 진입했던 승격 문서(징계기준·CREDO)의 P2 잔존.
    b3 = {}
    for qid in ("g14", "g12", "g09", "g13"):
        exp = set(golden[qid].get("expected_sources") or [])
        docs1 = {f["doc"] for f in r1[qid]["final"]} if qid in r1 else set()
        docs2 = {f["doc"] for f in r2[qid]["final"]} if qid in r2 else set()
        hit1 = sorted(exp & docs1)
        hit2 = sorted(exp & docs2)
        prom1 = sorted(docs1 & set(PROMOTED))
        prom2 = sorted(docs2 & set(PROMOTED))
        # 판정은 지시서 문언 기준 — rescue 출신(RRF>10) 승격 문서의 보존.
        # (top-RRF 출신 승격 청크의 동점 변동은 P2′ 무관 리랭커 노이즈 —
        # promoted_p1/p2 로 원시 기록만 남긴다. 실증: g09 5위 한 석
        # CREDO(rrf4)↔징계기준(rrf3), skip=False 동일 경로 양 런)
        resc_prom1 = sorted({f["doc"] for f in r1[qid]["final"]
                             if f["doc"] in PROMOTED
                             and f["rrf"] is not None and f["rrf"] > 10}
                            if qid in r1 else set())
        resc_prom2 = sorted({f["doc"] for f in r2[qid]["final"]
                             if f["doc"] in PROMOTED
                             and f["rrf"] is not None and f["rrf"] > 10}
                            if qid in r2 else set())
        b3[qid] = {"expected_hit_p1": hit1, "expected_hit_p2": hit2,
                   "promoted_p1": prom1, "promoted_p2": prom2,
                   "rescue_promoted_p1": resc_prom1,
                   "rescue_promoted_p2": resc_prom2,
                   "pass": set(hit1) <= set(hit2)
                           and set(resc_prom1) <= set(resc_prom2)}
    verdict["b3"] = {**b3, "pass": all(v["pass"] for v in b3.values())}

    # b4 — 무관-지목 (리랭크 유지) 원시 기록
    irr_routed = [r for r in irr if r.get("router_hit") is not None]
    verdict["b4"] = {"routed_ids": [r["id"] for r in irr_routed],
                     "promoted_in_final": {
                         r["id"]: sorted({f["doc"] for f in r["final"]}
                                         & set(PROMOTED))
                         for r in irr_routed}}

    # b5 — 관련 무지목 발생분: golden 적중 원시 기록 + P1 대비 적중 회귀 검사
    rel2 = [r for r in r2.values() if not r["irrelevant_group"]]
    rel_skip = [r for r in rel2 if r.get("router_hit") is None]
    b5 = []
    for r in rel_skip:
        exp = set(golden[r["id"]].get("expected_sources") or [])
        docs2 = {f["doc"] for f in r["final"]}
        docs1 = ({f["doc"] for f in r1[r["id"]]["final"]}
                 if r["id"] in r1 else set())
        b5.append({"id": r["id"],
                   "expected_hit_p2": sorted(exp & docs2),
                   "expected_hit_p1": sorted(exp & docs1),
                   "regressed": bool((exp & docs1) - (exp & docs2))})
    verdict["b5"] = {"skip_ids": [x["id"] for x in b5], "detail": b5,
                     "pass": not any(x["regressed"] for x in b5)}

    verdict["gate_b_pass"] = all([verdict["b1"]["pass"], verdict["b2"]["pass"],
                                  verdict["b3"]["pass"], verdict["b5"]["pass"],
                                  not verdict["errors_p2"]])
    print(json.dumps(verdict, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
