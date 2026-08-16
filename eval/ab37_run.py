"""지시서 003 — Gemini 3.7 Flash 오프라인 A/B 러너 (읽기 전용 평가, 엔진 0줄).

사용: python eval/ab37_run.py <base|A|B>
  base: 합성 gemini-3.6-flash + 리랭크 기본(gemini-3.5-flash-lite — 운영 현행)
  A:    합성 gemini-3.7-flash + 리랭크 기본        (합성 주 효과 분리)
  B:    합성 gemini-3.7-flash + 리랭크 gemini-3.7-flash

주의(지시서 표기 정정): 운영 리랭크 현행은 3.6 이 아니라 gemini-3.5-flash-lite
(2026-07-21 A/B 의결 기본값) — base/A 의 "리랭크 3.6" 은 "리랭크 현행"으로 수행.

문항: 골든 52(법령 3조건 분모 포함 53) + 홀드아웃 3(봉인 소비처 규약 준수).
토큰·finish_reason 계측은 synthesize 의 primary 주입(하니스 측 래퍼)으로 수행
— compass_engine 무수정. 결과는 무편집 JSON (eval/results/ab37_<run>_<ts>.json).
"""
from __future__ import annotations

import json
import os
import statistics as stats
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

RUN = sys.argv[1] if len(sys.argv) > 1 else "base"
CFG = {
    "base": {"NEXUS_CHAT_MODEL": "gemini-3.6-flash"},
    "A": {"NEXUS_CHAT_MODEL": "gemini-3.7-flash"},
    "B": {"NEXUS_CHAT_MODEL": "gemini-3.7-flash",
          "NEXUS_RERANK_MODEL": "gemini-3.7-flash"},
}[RUN]
os.environ.update(CFG)

import yaml  # noqa: E402
from compass_engine import synthesis as syn_mod  # noqa: E402
from eval import compare_v1v2 as cv  # noqa: E402
from eval.golden_ab import _score  # noqa: E402
from eval.runner import RESULTS_DIR, load_fixtures  # noqa: E402

_OOS_MARKERS = ("사규에서 확인되지 않", "확인되지 않는", "확인할 수 없")

STASH: dict = {}


def _gen_usage(system: str, user: str) -> str:
    """_gemini_gen 동일 동작 + usage_metadata·finish_reason 계측 (하니스 전용)."""
    from google import genai
    cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("NEXUS_CHAT_MODEL", "gemini-3.6-flash")
    res = cli.models.generate_content(
        model=model, contents=user,
        config={"system_instruction": system, "temperature": 0.0,
                "max_output_tokens": 4096},
    )
    um = getattr(res, "usage_metadata", None)
    STASH.setdefault("usage", []).append({
        "in": getattr(um, "prompt_token_count", None),
        "out": getattr(um, "candidates_token_count", None),
        "thoughts": getattr(um, "thoughts_token_count", None)})
    fr = ""
    try:
        fr = str(res.candidates[0].finish_reason.name)  # type: ignore[union-attr]
    except Exception:
        fr = ""
    STASH["finish_reason"] = fr or "STOP"
    if fr and fr != "STOP":
        raise syn_mod.TruncatedCompletion(f"finish_reason={fr}")
    return getattr(res, "text", "") or ""


_orig_synthesize = syn_mod.synthesize


def _synth(question, chunks, *, anchor_map=None, **kw):
    return _orig_synthesize(question, chunks, anchor_map=anchor_map,
                            primary=_gen_usage)


cv.synthesize = _synth   # Harness 는 모듈 전역 synthesize 를 호출


def main() -> int:
    h = cv.Harness()
    golden = load_fixtures(_ROOT / "eval" / "golden.yaml")
    holdout = yaml.safe_load((_ROOT / "eval" / "holdout.yaml")
                             .read_text(encoding="utf-8"))
    records, ho_records = [], []

    for i, e in enumerate(golden, 1):
        STASH.clear()
        rec: dict = {"id": e["id"], "category": e.get("category")}
        try:
            side = h.run_v2_side(e["question"])
            sc = _score(side["answer"], e, h.ledger)
            rec.update({
                "answer": side["answer"],
                "elapsed_total_s": side["elapsed_total_s"],
                "synth_ms": side["synth_ms"],
                "timings": side["timings"],
                "n_chunks": side["n_chunks"],
                "router_hit": side["router_hit"],
                "provider": side["provider"],
                "used_fallback": side["used_fallback"],
                "integrity_ok": side["integrity_ok"],
                "synth_retries": side["synth_retries"],
                "section_contract_ok": side["section_contract_ok"],
                "verify": side["verify"],
                "score": sc,
                "neg_marker_pass": (any(m in side["answer"] for m in _OOS_MARKERS)
                                    if e.get("category") == "negative" else None),
                "finish_reason": STASH.get("finish_reason", "STOP"),
                "usage": STASH.get("usage") or [],
            })
        except Exception as ex:   # 결측 정직 표기 (수용 기준 a)
            rec.update({"error": f"{type(ex).__name__}: {ex}"[:300],
                        "finish_reason": STASH.get("finish_reason"),
                        "usage": STASH.get("usage") or []})
        records.append(rec)
        v = rec.get("verify") or {}
        print(f"[{RUN}] {i}/{len(golden)} {e['id']} "
              f"grade={v.get('grade')} fr={rec.get('finish_reason')} "
              f"err={'error' in rec}", flush=True)

    strip = __import__("re").compile(r"^\([^)]{1,12}\)\s*")
    for r in holdout:
        STASH.clear()
        rec = {"id": r["id"]}
        try:
            side = h.run_v2_side(r["question"])
            ctx = side.get("context_docs") or []
            hit = any(any(e2 == c or strip.sub("", e2) == strip.sub("", c)
                          for c in ctx) for e2 in r["expected"])
            rec.update({"recovered": hit, "context_docs": ctx,
                        "answer": side["answer"],
                        "elapsed_total_s": side["elapsed_total_s"],
                        "verify": side["verify"],
                        "finish_reason": STASH.get("finish_reason", "STOP"),
                        "usage": STASH.get("usage") or []})
        except Exception as ex:
            rec.update({"error": f"{type(ex).__name__}: {ex}"[:300]})
        ho_records.append(rec)
        print(f"[{RUN}] holdout {r['id']} recovered={rec.get('recovered')}",
              flush=True)

    # ── 집계 (측정 10항 — 무편집 원시 records 동봉) ──
    ok_recs = [r for r in records if "error" not in r]
    pos = [r for r in ok_recs if r.get("category") != "negative"]
    neg = [r for r in ok_recs if r.get("category") == "negative"]
    exp_hit = sum(r["score"]["expected_hit"] for r in pos)
    exp_total = sum(r["score"]["expected_total"] for r in pos)
    fab = [r for r in ok_recs if r["score"].get("has_fabrication")]
    fab_nondeg = [r for r in fab if r["verify"]["action"] == "pass"]
    grades = {}
    for r in ok_recs:
        grades[r["verify"]["grade"]] = grades.get(r["verify"]["grade"], 0) + 1
    cite_ok = sum(r["verify"]["ok"] for r in ok_recs)
    cite_n = sum(r["verify"]["n"] for r in ok_recs)
    el = sorted(r["elapsed_total_s"] for r in ok_recs)
    tok_in = sum(u["in"] or 0 for r in records for u in r.get("usage") or [])
    tok_out = sum(u["out"] or 0 for r in records for u in r.get("usage") or [])
    tok_th = sum(u["thoughts"] or 0 for r in records for u in r.get("usage") or [])
    agg = {
        "1_recall": {"hit": exp_hit, "total": exp_total},
        "2_forgery": {"fab_answers": len(fab),
                      "fab_non_degraded": len(fab_nondeg),
                      "fab_ids": [r["id"] for r in fab]},
        "3_holdout": {"recovered": sum(1 for r in ho_records if r.get("recovered")),
                      "n": len(ho_records)},
        "4_grade_dist": grades,
        "5_contract_ok_rate": {
            "ok": sum(1 for r in ok_recs if r["section_contract_ok"]),
            "n": len(ok_recs)},
        "6_anchor_ok_rate": {"ok": cite_ok, "n": cite_n},
        "7_truncation": sum(1 for r in records
                            if (r.get("finish_reason") or "STOP") != "STOP"),
        "8_g02": {"fallback_used": sum(1 for r in ok_recs if r["used_fallback"]),
                  "resynth": sum(1 for r in ok_recs if r.get("synth_retries")),
                  "fallback_failed_errors": sum(
                      1 for r in records
                      if "error" in r and (r.get("finish_reason") or "STOP") != "STOP")},
        "9_latency": {"p50": el[len(el) // 2] if el else None,
                      "p95": el[max(0, int(len(el) * 0.95) - 1)] if el else None,
                      "mean": round(stats.mean(el), 2) if el else None},
        "10_tokens": {"in_sum": tok_in, "out_sum": tok_out,
                      "thoughts_sum": tok_th,
                      "per_q_in_mean": round(tok_in / max(1, len(records)), 1),
                      "per_q_out_mean": round(tok_out / max(1, len(records)), 1)},
        "negative_marker_pass": {"pass": sum(1 for r in neg if r.get("neg_marker_pass")),
                                 "n": len(neg)},
        "errors": [r["id"] for r in records if "error" in r],
    }
    out = {
        "run": RUN,
        "config": {"chat_model": os.environ["NEXUS_CHAT_MODEL"],
                   "rerank_model": os.environ.get("NEXUS_RERANK_MODEL",
                                                  "gemini-3.5-flash-lite(기본)")},
        "timestamp": datetime.now().isoformat(),
        "aggregates": agg,
        "records": records,
        "holdout_records": ho_records,
    }
    path = RESULTS_DIR / f"ab37_{RUN}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{RUN}] DONE → {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
