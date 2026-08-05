"""R3 재검증 이중 성적표 채점기 (신 기준 정본 + 구 기준 참고 병기).

신 기준 = 정정 골든(3조건형) × 정화 원장 × 신 매처.
구 기준 = 구 라벨(정정 3문항 원형 오버라이드) × 동일 원장 — 참고 병기용.
통과 기준 8종 + 라우터 유지, ②③은 정정 라벨 기준 판정 (R3 지시서).

사용: python eval/recert_score_r3.py <new.json> [holdout.json] [router.json]
"""
from __future__ import annotations

import copy
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
from eval.golden_ab import _law_ref_hit  # noqa: E402
from eval.runner import load_fixtures  # noqa: E402

OLD_RUN = _ROOT / "eval" / "results" / "compare_v1v2_20260728T114752.json"
BA_PAIRS = [("g03", "(영업) CSR경영방침", None),
            ("g04", "(공통) 중대 사건사고 보고지침", None),
            ("g04", "(공통) 일반 사건사고 보고지침", None),
            ("g13", "(영업) CSR경영방침", None),
            ("g40", "(CSR) 대외출강 운영 지침", None),
            ("g42", "(영업) CSR경영방침", None),
            ("g43", "(공통) 대외 민감정보 요구 대응 지침", None)]
D_IDS = ("g23", "g27", "g28", "g44", "g46")   # 정정 후 정의: 문항 전체 hit
# 구 라벨 원형 (참고 성적표용 오버라이드)
OLD_LABELS = {
    "g23": [{"doc": "(총무) 영상정보기기 설치운영 지침", "article": "제25조"},
            {"doc": "(총무) 영상정보기기 설치운영 지침", "article": "제25조의2"}],
    "g27": [{"doc": "(안전) 휴게시설 관리지침", "article": "제79조"}],
    "g28": [{"doc": "(공정거래) 협력회사 판촉비용 분담 지침", "article": "제11조"},
            {"doc": "(공정거래) 부당한 경영활동 간섭 및 경영정보 제공요구 금지 지침",
             "article": "제11조"}],
}
P50_LIMIT = 23.3
_strip = lambda t: re.sub(r"^\([^)]{1,12}\)\s*", "", t)  # noqa: E731


def pair_hits(entry: dict, rec: dict | None, ledger) -> dict:
    ans = "" if (rec is None or rec["v2"].get("failed")) else rec["v2"]["answer"]
    checks = check_citations(ans, ledger)
    okp = {(c.title, c.canonical) for c in checks if c.verdict == "ok"}
    out = {}
    for c in entry.get("expected_citations") or []:
        d, a = c["doc"], c.get("article")
        out[(entry["id"], d, a)] = (
            (d in ans or _strip(d) in ans) if a is None else (d, a) in okp)
    if entry.get("expected_law_refs"):
        out[(entry["id"], "__law__", None)] = _law_ref_hit(ans, entry, checks)
    return out


def score(entries, nrec, orec, ledger, tag) -> tuple[list, dict]:
    new_pairs, old_pairs = {}, {}
    for qid, e in entries.items():
        new_pairs.update(pair_hits(e, nrec.get(qid), ledger))
        old_pairs.update(pair_hits(e, orec.get(qid), ledger))
    res = []
    ba = [new_pairs.get(p, False) for p in BA_PAIRS]
    res.append((f"[{tag}] ① B+A' 7건 전건", all(ba),
                f"{sum(ba)}/7 미회수={[p[0] for p, h in zip(BA_PAIRS, ba) if not h]}"))
    dd = {q: all(h for (qq, _, _), h in new_pairs.items() if qq == q) for q in D_IDS}
    res.append((f"[{tag}] ② D 5건 ≥4", sum(dd.values()) >= 4,
                f"{sum(dd.values())}/5 {dd}"))
    prev_ok = [k for k, h in old_pairs.items() if h]
    reg = [k for k in prev_ok if not new_pairs.get(k)]
    res.append((f"[{tag}] ③ 구 통과 {len(prev_ok)}쌍 회귀", not reg, f"{reg}"))
    tot_h, tot_n = sum(new_pairs.values()), len(new_pairs)
    return res, {"recall": f"{tot_h}/{tot_n} ({tot_h/tot_n:.1%})",
                 "denominator": tot_n}


def main() -> int:
    from supabase import create_client
    newd = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    holdout = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")) \
        if len(sys.argv) > 2 else None
    rprobe = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) \
        if len(sys.argv) > 3 else None
    ledger = load_ledger(create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_ANON_KEY") or os.environ["SUPABASE_KEY"]))
    entries = {e["id"]: e for e in load_fixtures(_ROOT / "eval" / "golden.yaml")}
    old = {r["id"]: r for r in json.loads(OLD_RUN.read_text(encoding="utf-8"))["records"]}
    new = {r["id"]: r for r in newd["records"]}

    # 신 기준 (정본)
    results, agg_new = score(entries, new, old, ledger, "신")
    # 구 기준 (참고 — 정정 3문항 라벨 원형 오버라이드, 매처 law 경로 미사용)
    entries_old = copy.deepcopy(entries)
    for qid, labels in OLD_LABELS.items():
        entries_old[qid]["expected_citations"] = labels
        entries_old[qid].pop("expected_law_refs", None)
    results_old, agg_old = score(entries_old, new, old, ledger, "구")

    # 공통 기준 ④~⑧ + 라우터 (신 기준 성적표에만 판정 반영)
    negs = [q for q, e in entries.items() if e.get("category") == "negative"]
    neg_pass = sum(1 for q in negs if not new[q]["v2"].get("failed")
                   and new[q]["v2"]["score"].get("negative_pass"))
    results.append(("④ negative 6/6", neg_pass == 6, f"{neg_pass}/6"))
    leak, proxy_high, gate_used = [], [], []
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
            if v2.get("synth_retries"):
                gate_used.append((r["id"], v2.get("integrity_ok")))
    results.append(("⑤ 위조 비강등 유출 0", not leak, f"{leak}"))
    results.append(("⑥ 프록시 포함 HIGH 0", not proxy_high, f"{proxy_high}"))
    if holdout is not None:
        results.append(("⑦ 홀드아웃 회수", holdout["recovered"] == holdout["n"],
                        f"{holdout['recovered']}/{holdout['n']}"))
    lats = [r["v2"]["elapsed_total_s"] for r in newd["records"]
            if not r["v2"].get("failed")]
    chn = [r["v2"].get("n_chunks") for r in newd["records"]
           if not r["v2"].get("failed") and r["v2"].get("n_chunks") is not None]
    p50 = st.median(lats)
    p95 = sorted(lats)[min(len(lats) - 1, int(.95 * len(lats)))]
    results.append((f"⑧ p50 ≤ {P50_LIMIT}s", p50 <= P50_LIMIT,
                    f"p50={p50:.1f}s p95={p95:.1f}s 청크p50={st.median(chn) if chn else '?'}"))
    if rprobe is not None:
        results.append(("라우터 ≥90%", rprobe["hit_rate"] >= 0.9,
                        f"{rprobe['hits']}/{rprobe['n']} ({rprobe['hit_rate']:.1%})"))

    print("════ R3 이중 성적표 ════")
    ok_all = True
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
        if not name.startswith("[구]"):
            ok_all = ok_all and ok
    print(f"  (참고) 구 기준: " + " / ".join(
        f"{n.split('] ')[1]}={'P' if o else 'F'}({d})" for n, o, d in results_old))
    print(f"  재현율 신={agg_new['recall']} (분모 {agg_new['denominator']}) "
          f"/ 구 기준 분모 {agg_old['denominator']}")
    print(f"  g02 게이트 사용: {gate_used}")
    print(f"════ 종합(신 기준): {'전 기준 통과' if ok_all else 'FAIL 존재'} ════")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
