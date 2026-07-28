"""비교 하니스 순수 로직 — blindspot 태거(§6) + 지표 매트릭스 집계(§4).

전부 결정론 함수 (LLM·DB 접근 없음) — 오프라인 단위 테스트 대상.

§4 매트릭스 (★): 비교 판정은 양쪽 공통 지표(기대 인용 재현율·위조·negative·
지연)로만 한다. 섹션 계약·§5 verify 는 v2 전용 기록으로 병기.
§6 (★): blindspot 은 태그 + 이중 집계까지만 — 이 태그를 근거로 원장·정규화·
합성·verify 를 고치는 것은 H 심의 안건이라 하니스 범위에서 제외.
"""
from __future__ import annotations

import re
from typing import Any

# 실조항 판정: 제N조(의M) canonical 만 인정 — "부칙" 류는 실조항이 아님
_REAL_ARTICLE = re.compile(r"제\d+조(의\d+)?$")
_PREFIX = re.compile(r"^\([^)]{1,12}\)\s*")
# 쓰기성 RPC 이름 패턴 (스모크 ⑤ 실검사 — 감리 지적 2 보완)
_WRITE_RPC = re.compile(
    r"insert|update|upsert|delete|write|log_|_log\b|record|create|set_", re.I)


def suspicious_rpc_names(rpc_calls: dict) -> list[str]:
    """가드 로그의 RPC 이름 중 쓰기성으로 의심되는 것 — 스모크 ⑤ 판정 근거."""
    return sorted(n for n in rpc_calls if _WRITE_RPC.search(n))


def blindspot_titles(ledger: Any) -> set[str]:
    """파생 원장 기준 등재 실조항 0건(무등재 또는 부칙류뿐)인 문서 제목 집합.

    registry 조회만으로 판정 (결정론 — LLM 판단 금지, §6).
    """
    out: set[str] = set()
    for title, doc_id in ledger.title_to_doc_id.items():
        arts = ledger.articles_by_doc.get(doc_id) or set()
        if not any(_REAL_ARTICLE.fullmatch(str(a)) for a in arts):
            out.add(title)
    return out


def tag_blindspot(entry: dict, bs_titles: set[str]) -> dict:
    """golden 문항의 기대 인용 문서 중 blindspot 문서가 하나라도 있으면 태그.

    '하나라도' 기준인 이유: 그 문서 몫의 인용 채점이 구조적으로 불리해져
    문항 점수가 오염되기 때문. 과잉 태그는 이중 집계로 항상 가시화된다.
    """
    stripped_bs = {_PREFIX.sub("", t) for t in bs_titles}
    hits = []
    for c in entry.get("expected_citations") or []:
        doc = c.get("doc") or ""
        if doc in bs_titles or _PREFIX.sub("", doc) in stripped_bs:
            hits.append(doc)
    return {"blindspot": bool(hits), "docs": hits}


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def aggregate(records: list[dict], system: str,
              *, exclude_blindspot: bool = False) -> dict:
    """문항 레코드 → 시스템별 §4 매트릭스 집계.

    record 형태: {"blindspot": {...}, system: {"score": {...}, "elapsed_total_s",
    "failed"?}} — system 키 부재/failed 는 실패 카운트로 분리 (재시도 소진분).
    """
    agg = {"exp_hit": 0, "exp_total": 0, "fab_answers": 0, "answers": 0,
           "neg_pass": 0, "neg_total": 0, "failed": 0, "latency": []}
    for r in records:
        if exclude_blindspot and (r.get("blindspot") or {}).get("blindspot"):
            continue
        side = r.get(system)
        if not side or side.get("failed"):
            agg["failed"] += 1
            continue
        sc = side.get("score") or {}
        agg["answers"] += 1
        agg["exp_hit"] += sc.get("expected_hit", 0)
        agg["exp_total"] += sc.get("expected_total", 0)
        agg["fab_answers"] += 1 if sc.get("has_fabrication") else 0
        if "negative_pass" in sc:
            agg["neg_total"] += 1
            agg["neg_pass"] += 1 if sc["negative_pass"] else 0
        if side.get("elapsed_total_s") is not None:
            agg["latency"].append(float(side["elapsed_total_s"]))
    lat = agg.pop("latency")
    agg["recall"] = (agg["exp_hit"] / agg["exp_total"]) if agg["exp_total"] else None
    agg["latency_p50_s"] = _pct(lat, 0.5)
    agg["latency_p95_s"] = _pct(lat, 0.95)
    return agg


def matrix_report(records: list[dict]) -> dict:
    """전체 / blindspot 제외 이중 집계 (§6) — 양 시스템."""
    out: dict = {"blindspot_ids": [r["id"] for r in records
                                   if (r.get("blindspot") or {}).get("blindspot")]}
    for system in ("v1", "v2"):
        out[system] = {
            "all": aggregate(records, system),
            "excl_blindspot": aggregate(records, system, exclude_blindspot=True),
        }
    return out
