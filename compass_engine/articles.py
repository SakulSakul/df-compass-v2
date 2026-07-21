"""조항 정규화 — 레포 유일의 "제N조·제N조의M" 파서 [CLAUDE.md Part 2-C].

파서·적재기·§5 검증기·답변 인용 추출기가 전부 이 모듈을 import 한다.
복제·인라인 정규식 우회 금지 — 서로 다른 정규화는 오차단을, 같은 오류의 공유는
영구 미검출을 낳으므로 정규화는 여기 한 곳에만 존재한다.

v1 파서의 실제 결함: "제3조의2"를 "제3조"로 붕괴 → 본 구현은 조의N 을 보존한다.
지원 범위(phase-0 지시): 제N조 / 제N조의M / 부칙(부칙 제N조 포함) / 별표N / 삭제조항.

registry 포함/제외 정책(부칙·별표·삭제조항)은 적재 규칙의 몫이다(Phase 1) —
이 모듈은 '정규화와 추출'만 책임진다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, Literal, Optional

Kind = Literal["article", "addendum", "annex"]

# 제N조(의M): 공백 허용("제 3 조 의 2"), 뒤에 항·호가 붙어도 조 단위까지만 취한다.
_ARTICLE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
# 별표N (번호 생략 가능: "별표")
_ANNEX = re.compile(r"별표\s*(\d+)?")
# 부칙 (바로 뒤에 제N조가 이어지면 부칙 소속 조항)
_ADDENDUM = re.compile(r"부\s*칙")
# 조항 토큰 직후의 삭제 표기: "제5조 삭제", "제5조(삭제)", "제5조 <삭제>"
_DELETED_AFTER = re.compile(r"^\s*[\(<〈\[]?\s*삭\s*제")


@dataclass(frozen=True, order=False)
class ArticleRef:
    """정규화된 조항 참조.

    canonical 이 registry 대조 키다 — 예: "제3조의2", "부칙 제2조", "별표1", "부칙".
    """
    kind: Kind
    main_no: Optional[int]            # article/annex 번호. addendum 단독이면 None
    sub_no: Optional[int] = None      # 조의M 의 M
    deleted: bool = False             # 원문에 삭제 표기가 붙어 있었는지

    @property
    def canonical(self) -> str:
        if self.kind == "annex":
            return f"별표{self.main_no}" if self.main_no is not None else "별표"
        base = ""
        if self.main_no is not None:
            base = f"제{self.main_no}조" + (f"의{self.sub_no}" if self.sub_no is not None else "")
        if self.kind == "addendum":
            return f"부칙 {base}".strip()
        return base

    @property
    def sort_key(self) -> tuple:
        kind_order = {"article": 0, "addendum": 1, "annex": 2}[self.kind]
        return (kind_order, self.main_no or 0, self.sub_no or 0)


def parse_article_ref(token: str) -> Optional[ArticleRef]:
    """단일 토큰을 정규화. 조항 표기가 아니면 None.

    "제3조의2" → article(3, 2)  /  "부칙 제2조" → addendum(2)  /  "별표 1" → annex(1)
    "제3조 제2항" → article(3) — registry 는 조 단위이므로 항·호는 버린다.
    """
    if token is None:
        return None
    s = token.strip()
    if not s:
        return None

    add = _ADDENDUM.search(s)
    art = _ARTICLE.search(s)
    if add is not None:
        if art is not None and art.start() > add.start():
            return ArticleRef("addendum", int(art.group(1)),
                              int(art.group(2)) if art.group(2) else None)
        return ArticleRef("addendum", None)
    if art is not None:
        return ArticleRef("article", int(art.group(1)),
                          int(art.group(2)) if art.group(2) else None)
    annex = _ANNEX.search(s)
    if annex is not None:
        return ArticleRef("annex", int(annex.group(1)) if annex.group(1) else None)
    return None


def _iter_refs(text: str) -> Iterator[ArticleRef]:
    # 부칙 구간: "부칙" 등장 이후의 제N조는 부칙 소속으로 본다.
    # (사규 원문·답변 인용 모두 "부칙 제2조"가 한 호흡으로 나온다 — 근접 40자 제한)
    addendum_spans = [(m.start(), m.end()) for m in _ADDENDUM.finditer(text)]

    def in_addendum(pos: int) -> bool:
        return any(end <= pos <= end + 40 for _, end in addendum_spans)

    consumed_article_positions = set()
    for m in _ARTICLE.finditer(text):
        consumed_article_positions.add(m.start())
        deleted = bool(_DELETED_AFTER.match(text[m.end():m.end() + 8]))
        kind: Kind = "addendum" if in_addendum(m.start()) else "article"
        yield ArticleRef(kind, int(m.group(1)),
                         int(m.group(2)) if m.group(2) else None, deleted)

    for m in _ADDENDUM.finditer(text):
        # 뒤따르는 제N조가 없으면 '부칙' 단독 참조
        following = _ARTICLE.search(text, m.end(), m.end() + 40)
        if following is None:
            yield ArticleRef("addendum", None)

    for m in _ANNEX.finditer(text):
        yield ArticleRef("annex", int(m.group(1)) if m.group(1) else None)


def extract_article_refs(text: str) -> list[ArticleRef]:
    """자유 텍스트(답변·사규 원문)에서 조항 참조를 전부 추출 — 중복 제거·정렬.

    deleted 여부가 다른 동일 조항은 deleted=True 쪽을 남긴다(보수적).
    """
    if not text:
        return []
    best: dict[tuple, ArticleRef] = {}
    for ref in _iter_refs(text):
        key = (ref.kind, ref.main_no, ref.sub_no)
        if key not in best or (ref.deleted and not best[key].deleted):
            best[key] = ref
    return sorted(best.values(), key=lambda r: r.sort_key)
