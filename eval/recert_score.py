"""재검증 통과 기준 채점기 (구현 지시서 v1 — 사전 고정, 사후 완화 금지).

기준: ① B+A' 7건 전건 회수 ② D 5건 ≥4 ③ 기존 통과 38쌍 신규 미스 0
④ neg 6/6 ⑤ 위조 비강등 유출 0 ⑥ 프록시 포함인데 HIGH 0건
⑦ 홀드아웃 3문항 회수(별도 holdout_run 결과 인자) ⑧ p50 ≤ 23.3s
(청크 수 병기·p95 기록만). 라우터 정확도(≥90%)는 router_probe 재실행분 인자.

사용: python eval/recert_score.py <new_compare.json> [holdout.json] [router_probe.json]
기준 대상 쌍은 골든 원본에서 재채점 (구 러닝 대비 diff — 진단서 §1 과 동일 방법).
"""
from __future__ import annotations

import json
import os
import re
import statistics as st
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from compass_engine.citations import check_citations  # noqa: E402
from compass_engine.proxies import PROXY_DOCS  # noqa: E402
from compass_engine.registry import load_ledger  # noqa: E402
from eval.runner import load_fixtures  # noqa: E402

OLD_PATH = _ROOT / "eval" / "results" / "compare_v1v2_20260728T114752.json"
# 진단서 §1 확정 미스 계급 (사전 고정)
BA_PAIRS = [("g03", "(영업) CSR경영방침", None),
            ("g04", "(공통) 중대 사건사고 보고지침", None),
            ("g04", "(공통) 일반 사건사고 보고지침", None),
            ("g13", "(영업) CSR경영방침", None),
            ("g40", "(CSR) 대외출강 운영 지침", None),
            ("g42", "(영업) CSR경영방침", None),
            ("g43", "(공통) 대외 민감정보 요구 대응 지침", None)]
D_PAIRS = [("g23", "(총무) 영상정보기기 설치운영 지침", "제25조"),
           ("g27", "(안전) 휴게시설 관리지침", "제79조"),
           ("g28", "(공정거래) 부당한 경영활동 간섭 및 경영정보 제공요구 금지 지침", "제11조"),
           ("g44", "(CSR) 클린뱅크 운영 지침", "제4조"),
           ("g46", "(CSR) 클린뱅크 운영 지침", "제3조")]
P50_LIMIT = 23.3

_strip = lambda t: re.sub(r"^\([^)]{1,12}\)\s*", "", t)  # noqa: E731


def _pair_hit(answer: str, doc: str, art: str | None, ledger) -> bool:
    if art is None:
        return doc in answer or _strip(doc) in answer
    ok_pairs = {(c.title, c.canonical)
                for c in check_citations(answer, ledger) if c.verdict == "ok"}
    return (doc, art) in ok_pairs


def _all_pairs(records: dict, entries: dict, ledger) -> dict:
    """{(id, doc, art): hit} — v2 답변 기준, 실패 문항은 miss 처리."""
    out = {}
    for qid, e in entries.items():
        rec = records.get(qid)
        ans = "" if (rec is None or rec["v2"].get("failed")) else rec["v2"]["answer"]
        for c in e.get("expected_citations") or []:
            out[(qid, c["doc"], c.get("article"))] = _pair_hit(
                ans, c["doc"], c.get("article"), ledger)
    return out


def main() -> int:
    from supabase import create_client
    new_path = Path(sys.argv[1])
    holdout = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")) \
        if len(sys.argv) > 2 else None
    rprobe = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) \
        if len(sys.argv) > 3 else None

    ledger = load_ledger(create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_ANON_KEY") or os.environ["SUPABASE_KEY"]))
    entries = {e["id"]: e for e in load_fixtures(_ROOT / "eval" / "golden.yaml")}
    old = {r["id"]: r for r in json.loads(OLD_PATH.read_text(encoding="utf-8"))["records"]}
    newd = json.loads(new_path.read_text(encoding="utf-8"))
    new = {r["id"]: r for r in newd["records"]}

    old_pairs = _all_pairs(old, entries, ledger)
    new_pairs = _all_pairs(new, entries, ledger)

    results: list[tuple[str, bool, str]] = []
    # ① B+A' 7건 전건
    ba = [new_pairs.get((i, d, a), False) for i, d, a in BA_PAIRS]
    results.append(("① B+A' 7건 전건 회수", all(ba),
                    f"{sum(ba)}/7 (미회수: {[p[0] for p, h in zip(BA_PAIRS, ba) if not h]})"))
    # ② D ≥4
    dd = [new_pairs.get((i, d, a), False) for i, d, a in D_PAIRS]
    results.append(("② D 5건 중 ≥4 회수", sum(dd) >= 4,
                    f"{sum(dd)}/5 (미회수: {[p[0] for p, h in zip(D_PAIRS, dd) if not h]})"))
    # ③ 기존 통과 쌍 회귀 0
    prev_ok = [k for k, h in old_pairs.items() if h]
    regressed = [k for k in prev_ok if not new_pairs.get(k, False)]
    results.append((f"③ 기존 통과 {len(prev_ok)}쌍 신규 미스 0", not regressed,
                    f"회귀 {len(regressed)}: {regressed}"))
    # ④ negative 6/6
    negs = [qid for qid, e in entries.items() if e.get("category") == "negative"]
    neg_pass = sum(1 for qid in negs
                   if not new[qid]["v2"].get("failed")
                   and new[qid]["v2"]["score"].get("negative_pass"))
    results.append(("④ negative 6/6", neg_pass == 6, f"{neg_pass}/6"))
    # ⑤ 위조 비강등 유출 0  ⑥ 프록시 포함 HIGH 0
    leak, proxy_high = [], []
    for pool in (newd["records"], newd["variant_track"]["records"]):
        for r in pool:
            v2 = r.get("v2")
            if not v2 or v2.get("failed"):
                continue
            if v2["score"].get("has_fabrication") and v2["verify"]["action"] == "pass":
                leak.append(r["id"])
            if v2["verify"].get("grade") == "HIGH" and \
                    any(t in v2["answer"] for t in PROXY_DOCS):
                proxy_high.append(r["id"])
    results.append(("⑤ 위조 비강등 유출 0 (골든+변형)", not leak, f"{leak}"))
    results.append(("⑥ 프록시 포함 HIGH 0건", not proxy_high, f"{proxy_high}"))
    # ⑦ 홀드아웃
    if holdout is not None:
        results.append(("⑦ 홀드아웃 3문항 회수", holdout["recovered"] == holdout["n"],
                        f"{holdout['recovered']}/{holdout['n']}"))
    # ⑧ p50 (+청크 수 병기·p95 기록)
    lats = [r["v2"]["elapsed_total_s"] for r in newd["records"]
            if not r["v2"].get("failed")]
    chn = [r["v2"].get("n_chunks") for r in newd["records"]
           if not r["v2"].get("failed") and r["v2"].get("n_chunks") is not None]
    p50, p95 = st.median(lats), sorted(lats)[min(len(lats) - 1, int(.95 * len(lats)))]
    results.append((f"⑧ p50 ≤ {P50_LIMIT}s", p50 <= P50_LIMIT,
                    f"p50={p50:.1f}s p95={p95:.1f}s(기록만) 청크 p50={st.median(chn) if chn else '?'}"))
    # 라우터 정확도
    if rprobe is not None:
        results.append(("라우터 정확도 ≥90%", rprobe["hit_rate"] >= 0.9,
                        f"{rprobe['hits']}/{rprobe['n']} ({rprobe['hit_rate']:.1%})"))

    print("════ 재검증 통과 기준 채점 ════")
    ok_all = True
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
        ok_all = ok_all and ok
    print(f"════ 종합: {'전 기준 통과' if ok_all else 'FAIL 존재 — 정지 조건 검토'} ════")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
