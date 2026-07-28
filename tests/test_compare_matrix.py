"""blindspot 태거(§6)·매트릭스 집계(§4) 오프라인 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compass_engine.registry import ArticleLedger  # noqa: E402
from eval.compare_matrix import (  # noqa: E402
    aggregate, blindspot_titles, matrix_report, suspicious_rpc_names,
    tag_blindspot)


def test_suspicious_rpc_names():
    # 스모크 ⑤ 실검사 — 실측 관찰된 v1 읽기 RPC 는 통과, 쓰기성 이름은 검출
    reads = {"nexus_hybrid_search_v2": 3, "nexus_diagnose_role": 1,
             "nexus_force_include_chunks_by_incident_nodes": 2}
    assert suspicious_rpc_names(reads) == []
    assert suspicious_rpc_names({**reads, "nexus_insert_feedback": 1,
                                 "set_config": 1}) == [
        "nexus_insert_feedback", "set_config"]


def _ledger() -> ArticleLedger:
    return ArticleLedger(
        articles_by_doc={"d1": {"제1조", "제2조의2"}, "d2": {"부칙"}, "d3": set()},
        title_to_doc_id={"(안전) 산업안전 규정": "d1",
                         "(인사) 직장 내 괴롭힘 예방·대응지침": "d2",
                         "(총무) 무조항 지침": "d3"},
        doc_id_to_title={"d1": "(안전) 산업안전 규정",
                         "d2": "(인사) 직장 내 괴롭힘 예방·대응지침",
                         "d3": "(총무) 무조항 지침"},
    )


def test_blindspot_titles_only_no_real_article_docs():
    bs = blindspot_titles(_ledger())
    # 실조항(제N조/제N조의M) 보유 문서는 제외, 부칙뿐·무등재 문서만 태그
    assert bs == {"(인사) 직장 내 괴롭힘 예방·대응지침", "(총무) 무조항 지침"}


def test_tag_blindspot_any_expected_doc():
    bs = blindspot_titles(_ledger())
    tagged = tag_blindspot(
        {"expected_citations": [
            {"doc": "(안전) 산업안전 규정", "article": "제1조"},
            {"doc": "(인사) 직장 내 괴롭힘 예방·대응지침", "article": None}]},
        bs)
    assert tagged["blindspot"] is True
    assert tagged["docs"] == ["(인사) 직장 내 괴롭힘 예방·대응지침"]
    clean = tag_blindspot(
        {"expected_citations": [{"doc": "(안전) 산업안전 규정",
                                 "article": "제1조"}]}, bs)
    assert clean == {"blindspot": False, "docs": []}
    # negative 류 (기대 인용 없음) 는 blindspot 아님
    assert tag_blindspot({}, bs)["blindspot"] is False


def test_tag_blindspot_prefix_stripped_title():
    bs = {"(인사) 직장 내 괴롭힘 예방·대응지침"}
    tagged = tag_blindspot(
        {"expected_citations": [{"doc": "직장 내 괴롭힘 예방·대응지침",
                                 "article": None}]}, bs)
    assert tagged["blindspot"] is True


def _records() -> list[dict]:
    return [
        {"id": "g1", "blindspot": {"blindspot": False, "docs": []},
         "v1": {"score": {"expected_hit": 1, "expected_total": 2,
                          "has_fabrication": False}, "elapsed_total_s": 10.0},
         "v2": {"score": {"expected_hit": 2, "expected_total": 2,
                          "has_fabrication": False}, "elapsed_total_s": 5.0}},
        {"id": "g2", "blindspot": {"blindspot": True, "docs": ["x"]},
         "v1": {"score": {"expected_hit": 0, "expected_total": 1,
                          "has_fabrication": True}, "elapsed_total_s": 20.0},
         "v2": {"score": {"expected_hit": 0, "expected_total": 1,
                          "has_fabrication": False}, "elapsed_total_s": 6.0}},
        {"id": "g3", "blindspot": {"blindspot": False, "docs": []},
         "v1": {"failed": True, "error": "boom"},
         "v2": {"score": {"expected_hit": 0, "expected_total": 0,
                          "has_fabrication": False, "negative_pass": True},
                "elapsed_total_s": 4.0}},
    ]


def test_aggregate_full_and_excl_blindspot():
    recs = _records()
    a_v1 = aggregate(recs, "v1")
    assert (a_v1["exp_hit"], a_v1["exp_total"]) == (1, 3)
    assert a_v1["fab_answers"] == 1 and a_v1["failed"] == 1
    ex_v1 = aggregate(recs, "v1", exclude_blindspot=True)
    assert (ex_v1["exp_hit"], ex_v1["exp_total"]) == (1, 2)
    assert ex_v1["fab_answers"] == 0            # 위조가 blindspot 문항에만 있던 경우
    a_v2 = aggregate(recs, "v2")
    assert a_v2["recall"] == 2 / 3
    assert (a_v2["neg_pass"], a_v2["neg_total"]) == (1, 1)
    assert a_v2["failed"] == 0
    assert a_v2["latency_p50_s"] == 5.0


def test_matrix_report_shape():
    rep = matrix_report(_records())
    assert rep["blindspot_ids"] == ["g2"]
    for system in ("v1", "v2"):
        assert set(rep[system]) == {"all", "excl_blindspot"}
