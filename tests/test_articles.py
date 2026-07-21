"""compass_engine.articles 단위 테스트 [Phase 0 필수].

핵심 계약: "제3조의2"가 "제3조"로 붕괴하면 실패해야 한다 (v1 파서의 실제 결함).
"""
from compass_engine.articles import ArticleRef, extract_article_refs, parse_article_ref


# ── 조의N 보존 (v1 결함 회귀 방지 — 이 테스트가 이 모듈의 존재 이유) ──
def test_article_sub_no_is_preserved():
    ref = parse_article_ref("제3조의2")
    assert ref == ArticleRef("article", 3, 2)
    assert ref.canonical == "제3조의2"
    assert ref.canonical != "제3조"


def test_sub_no_collapse_is_detectable():
    assert parse_article_ref("제3조의2") != parse_article_ref("제3조")


def test_multi_digit_sub_no():
    assert parse_article_ref("제10조의12") == ArticleRef("article", 10, 12)


# ── 기본형·공백 변형 ──────────────────────────────────────────────
def test_plain_article():
    assert parse_article_ref("제7조") == ArticleRef("article", 7, None)


def test_spacing_variants():
    assert parse_article_ref("제 3 조 의 2") == ArticleRef("article", 3, 2)
    assert parse_article_ref("제  15  조") == ArticleRef("article", 15, None)


def test_hang_and_ho_are_dropped_to_article_level():
    # registry 는 조 단위 — 항·호는 버린다
    assert parse_article_ref("제3조 제2항").canonical == "제3조"
    assert parse_article_ref("제3조제1항제2호").canonical == "제3조"


def test_non_article_returns_none():
    assert parse_article_ref("징계 절차 안내") is None
    assert parse_article_ref("") is None
    assert parse_article_ref(None) is None


# ── 부칙 ─────────────────────────────────────────────────────────
def test_addendum_alone():
    assert parse_article_ref("부칙") == ArticleRef("addendum", None)
    assert parse_article_ref("부칙").canonical == "부칙"


def test_addendum_article():
    ref = parse_article_ref("부칙 제2조")
    assert ref == ArticleRef("addendum", 2, None)
    assert ref.canonical == "부칙 제2조"


def test_addendum_differs_from_body_article():
    assert parse_article_ref("부칙 제2조") != parse_article_ref("제2조")


# ── 별표 ─────────────────────────────────────────────────────────
def test_annex():
    assert parse_article_ref("별표 1") == ArticleRef("annex", 1)
    assert parse_article_ref("별표3").canonical == "별표3"
    assert parse_article_ref("별표") == ArticleRef("annex", None)


# ── 삭제조항 ──────────────────────────────────────────────────────
def test_deleted_marker_detected_in_extraction():
    refs = extract_article_refs("제4조 삭제 <2019. 3. 1.>")
    assert refs == [ArticleRef("article", 4, None, deleted=True)]


def test_deleted_marker_with_bracket():
    refs = extract_article_refs("제6조(삭제)")
    assert refs[0].deleted is True


def test_non_deleted_not_flagged():
    refs = extract_article_refs("제5조(휴가) 임직원은…")
    assert refs == [ArticleRef("article", 5, None, deleted=False)]


# ── 자유 텍스트 추출 ──────────────────────────────────────────────
def test_extract_from_answer_text():
    text = ("취업규칙 제12조와 제12조의3, 그리고 윤리강령 제 3 조에 따라… "
            "자세한 절차는 별표 2 및 부칙 제2조 참조.")
    refs = extract_article_refs(text)
    canon = [r.canonical for r in refs]
    assert canon == ["제3조", "제12조", "제12조의3", "부칙 제2조", "별표2"]


def test_extract_dedupes():
    refs = extract_article_refs("제9조 … 제9조 … 제 9 조")
    assert len(refs) == 1


def test_extract_orders_by_number_not_appearance():
    refs = extract_article_refs("제23조와 제3조의2와 제3조")
    assert [r.canonical for r in refs] == ["제3조", "제3조의2", "제23조"]


def test_similar_article_confusion_pair_distinct():
    # G3 testset 의 유사 조항 혼동 케이스(제23조↔제32조류)가 파서 수준에서 구분되는지
    refs = extract_article_refs("제23조 및 제32조")
    assert [r.canonical for r in refs] == ["제23조", "제32조"]


def test_empty_text():
    assert extract_article_refs("") == []
    assert extract_article_refs(None) == []
