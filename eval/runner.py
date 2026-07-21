"""DF COMPASS v2 · 검색 수준 eval — 공유 runner (v1 eval/runner.py 이식).

v1 과의 차이:
- retrieval 을 v1 retrieve_for_eval(우회 함수) 대신 **엔진 계약의 Retriever
  프로토콜**(compass_engine.stages)로 받는다 — ADR-1(엔진/UI 분리)의 eval 측
  구현이자, retrieve 교체형 인터페이스(eval A/B)의 소비자.
- 문서 제목은 RetrievedChunk.breadcrumb 의 첫 세그먼트("문서명>...")에서 얻는다.
- 인용 수준 스코어러는 Phase 1 — 여기 없다 (phase-0 지시).

채점 규칙은 v1 과 동일 (baseline 비교 가능성 유지):
- expected substring ⊆ hit doc title 이면 매치.
- negative fixture: hit 0건이면 pass.
- pass 기준: recall >= 0.5 (starter baseline).
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compass_engine.stages import (  # noqa: E402
    IntakeResult, Retriever, RetrieveResult, RouteResult,
)

DEFAULT_FIXTURES = ROOT / "eval" / "fixtures.yaml"
RESULTS_DIR = ROOT / "eval" / "results"


@dataclass
class FixtureResult:
    id: str
    category: str
    question: str
    expected: list[str]
    hit_titles: list[str]
    precision: float
    recall: float
    best_score: float
    hit_count: int
    passed: bool
    note: str = ""


@dataclass
class RunSummary:
    timestamp: str
    fixtures_path: str
    provider: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    score_min: float = 0.0
    score_max: float = 0.0
    score_avg: float = 0.0
    by_category: dict[str, dict[str, float]] = field(default_factory=dict)
    fixtures: list[FixtureResult] = field(default_factory=list)


def load_fixtures(path: Path | str = DEFAULT_FIXTURES) -> list[dict]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError("PyYAML 미설치 — `pip install pyyaml` 필요.") from e
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError(f"{p} 는 list of fixture 형식이어야 합니다.")
    return data


def _stub_intake(question: str) -> IntakeResult:
    """검색 수준 eval 은 intake 를 통과한 일반 질의를 가정 (critical/OOS/FAQ 미적중)."""
    return IntakeResult(
        masked_text=question, is_critical=False, critical_matches=[],
        oos=False, faq_hit_id=None, ambiguity=None,
    )


_ROUTE_RULE: RouteResult = {"tracks": ["rule"], "intent": "eval"}


def _doc_title(breadcrumb: str) -> str:
    return (breadcrumb or "").split(">")[0]


def _match_expected(hit_title: str, expected_substrings: list[str]) -> bool:
    return any(s and s in (hit_title or "") for s in expected_substrings)


def evaluate_one(retriever: Retriever, fx: dict, *, top_k: int = 3) -> FixtureResult:
    fid = str(fx.get("id", ""))
    question = str(fx.get("question", "")).strip()
    expected = list(fx.get("expected_sources") or [])
    category = str(fx.get("category", "general"))

    try:
        result: RetrieveResult = retriever.retrieve(_stub_intake(question), _ROUTE_RULE)
        chunks = (result.get("chunks") or [])[:top_k]
    except Exception as e:
        return FixtureResult(
            id=fid, category=category, question=question,
            expected=expected, hit_titles=[],
            precision=0.0, recall=0.0, best_score=0.0, hit_count=0,
            passed=False, note=f"retrieval error: {type(e).__name__}: {e}",
        )

    hit_titles = [_doc_title(c.get("breadcrumb") or "") for c in chunks]
    scores = [float(c.get("score") or 0.0) for c in chunks]
    best_score = max(scores) if scores else 0.0
    hit_count = len(chunks)

    if category == "negative" or not expected:
        passed = (hit_count == 0)
        return FixtureResult(
            id=fid, category=category, question=question,
            expected=expected, hit_titles=hit_titles,
            precision=1.0 if passed else 0.0, recall=1.0,
            best_score=best_score, hit_count=hit_count,
            passed=passed, note="negative case — hit 0건 expected",
        )

    matched_titles = [t for t in hit_titles if _match_expected(t, expected)]
    matched_expected = [s for s in expected if any(s in t for t in hit_titles if t)]
    precision = (len(matched_titles) / hit_count) if hit_count else 0.0
    recall = (len(matched_expected) / len(expected)) if expected else 0.0

    return FixtureResult(
        id=fid, category=category, question=question,
        expected=expected, hit_titles=hit_titles,
        precision=precision, recall=recall,
        best_score=best_score, hit_count=hit_count,
        passed=recall >= 0.5,
    )


def summarize(results: list[FixtureResult], fixtures_path: str,
              provider: str = "") -> RunSummary:
    summary = RunSummary(
        timestamp=datetime.now().isoformat(),
        fixtures_path=fixtures_path, provider=provider,
        total=len(results),
        passed=sum(1 for r in results if r.passed),
    )
    summary.failed = summary.total - summary.passed
    if results:
        summary.avg_precision = sum(r.precision for r in results) / len(results)
        summary.avg_recall = sum(r.recall for r in results) / len(results)
        scores = [r.best_score for r in results]
        summary.score_min, summary.score_max = min(scores), max(scores)
        summary.score_avg = sum(scores) / len(scores)
    by_cat: dict[str, list[FixtureResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    for cat, lst in by_cat.items():
        summary.by_category[cat] = {
            "total": len(lst),
            "passed": sum(1 for r in lst if r.passed),
            "avg_precision": sum(r.precision for r in lst) / len(lst),
            "avg_recall": sum(r.recall for r in lst) / len(lst),
            "score_avg": sum(r.best_score for r in lst) / len(lst),
        }
    summary.fixtures = results
    return summary


def run_all(
    retriever: Retriever, *,
    fixtures_path: Path | str = DEFAULT_FIXTURES,
    top_k: int = 3,
    on_progress: Callable[[int, int, FixtureResult], None] | None = None,
) -> RunSummary:
    fixtures = load_fixtures(fixtures_path)
    results: list[FixtureResult] = []
    provider = ""
    for i, fx in enumerate(fixtures, start=1):
        r = evaluate_one(retriever, fx, top_k=top_k)
        results.append(r)
        if on_progress is not None:
            try:
                on_progress(i, len(fixtures), r)
            except Exception:
                pass
    try:
        probe = retriever.retrieve(_stub_intake("provider probe"), _ROUTE_RULE)
        provider = str(probe.get("provider") or "")
    except Exception:
        provider = "unknown"
    return summarize(results, str(fixtures_path), provider)


def write_results_json(summary: RunSummary, *,
                       results_dir: Path | str = RESULTS_DIR) -> Path:
    d = Path(results_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, ensure_ascii=False, indent=2)
    return out
