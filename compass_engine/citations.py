"""§5 인용 추출·대조 코어 — 답변에서 (문서명, 조항) 쌍을 뽑아 파생 원장과
결정론 대조한다. 인용 스코어러(eval)와 조항 검증기(verify 스테이지)가 공유.

LLM 판단이 아니라 조회다 (품질 서열 1위 — 無인용 무결성).
조항 정규식은 articles.py 단일 모듈만 사용 (Part 2-C).

판정(§5 3분기 + 스코어러 확장 1):
- ok               : (실재 문서, 실재 조항) — 또는 문서 단위 인용에 실재 문서
- article_missing  : 문서는 있는데 그 조항이 원장에 없음 (비실재 조항 인용)
- document_missing : 인용 형식에 잡힌 문서명이 원장에 없음 (비실재 문서)
- unattributed     : 조항 번호가 있는데 근처에 문서 귀속이 없음 (검증 불가 인용)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .articles import find_article_refs
from .registry import ArticleLedger

Verdict = Literal["ok", "article_missing", "document_missing", "unattributed"]

# 조항 참조 앞에서 문서 귀속을 인정하는 최대 거리(문자).
# "(문서명, 제N조)" 관용형이 대부분 이 안에 든다.
_PAIR_WINDOW = 100

# 관용 인용형에서 미지 문서명 추출: "(문서명, 제N조" / "((CSR) 문서명, 제3조의2"
_CITE_FORM = re.compile(
    r"[（(]\s*((?:\([^)]{1,30}\)\s*)?[^,，()（）\n]{2,60}?)\s*[,，]\s*(?=제\s*\d+\s*조)"
)


@dataclass
class CitationCheck:
    title: str | None          # 귀속 문서명 (unattributed 면 None)
    canonical: str | None      # 조항 정규형 (문서 단위 인용이면 None)
    verdict: Verdict
    position: int              # 답변 내 위치 (감사용)


_PREFIX = re.compile(r"^\([^)]{1,12}\)\s*")   # "(인사) ", "(CSR) " 류 부서 접두어


def _resolve_title(cited: str, ledger: ArticleLedger) -> str | None:
    """인용 문서명 → 원장 정식 제목. 접두어 생략 표기 허용.

    실측(2026-07-22 소급 채점 표본): 모델이 "(인사) 직장 내 괴롭힘 예방·대응지침"
    을 "직장 내 괴롭힘 예방·대응지침"으로 인용 — 실재 문서의 자연 표기를
    document_missing 으로 오분류하던 갭. 유일 매칭일 때만 해석(모호하면 None).
    """
    if ledger.has_document_title(cited):
        return cited
    matches = [t for t in ledger.title_to_doc_id
               if _PREFIX.sub("", t) == cited]
    return matches[0] if len(matches) == 1 else None


def _title_occurrences(answer: str, ledger: ArticleLedger) -> list[tuple[int, int, str]]:
    """원장 실재 문서명의 답변 내 전 출현 (start, end, title)."""
    occs: list[tuple[int, int, str]] = []
    for title in ledger.title_to_doc_id:
        start = 0
        while True:
            i = answer.find(title, start)
            if i < 0:
                break
            occs.append((i, i + len(title), title))
            start = i + 1
    occs.sort()
    return occs


def check_citations(answer: str, ledger: ArticleLedger) -> list[CitationCheck]:
    """답변 전체의 인용 쌍 추출 + 원장 대조 (결정론)."""
    if not answer:
        return []
    checks: list[CitationCheck] = []
    title_occs = _title_occurrences(answer, ledger)

    # 관용 인용형의 문서명 후보 (미지 문서 = document_missing 탐지용)
    cite_titles = [(m.start(1), m.end(1), m.group(1).strip())
                   for m in _CITE_FORM.finditer(answer)]

    for ref, start, _end in find_article_refs(answer):
        # ① 직접 인용형 "(문서명, 제N조)" 이 최우선 — 조항 직전(≤10자)의
        #   관용형 문서명은 원거리의 실재 문서명 출현보다 강한 귀속 신호다.
        #   (실재 제목이 근처에 있다고 위조 문서 인용을 article_missing 으로
        #    오분류하던 결함 수정 — 테스트로 검출)
        cited = None
        for c_start, c_end, cand in cite_titles:
            if c_end <= start and start - c_end <= 10:
                cited = cand
        if cited is not None:
            resolved = _resolve_title(cited, ledger)
            if resolved is not None:
                checks.append(CitationCheck(
                    title=resolved, canonical=ref.canonical,
                    verdict=ledger.verify(resolved, ref.canonical), position=start,
                ))
            else:
                checks.append(CitationCheck(
                    title=cited, canonical=ref.canonical,
                    verdict="document_missing", position=start,
                ))
            continue
        # ② 근접 선행하는 '실재 문서명' 귀속 (관용형 아님 — 서술형 인용)
        best = None
        for t_start, t_end, title in title_occs:
            if t_end <= start and start - t_end <= _PAIR_WINDOW:
                best = (t_end, title)
        if best is not None:
            title = best[1]
            checks.append(CitationCheck(
                title=title, canonical=ref.canonical,
                verdict=ledger.verify(title, ref.canonical), position=start,
            ))
            continue
        # ③ 귀속 불가
        checks.append(CitationCheck(
            title=None, canonical=ref.canonical,
            verdict="unattributed", position=start,
        ))
    return checks


def summarize_checks(checks: list[CitationCheck]) -> dict:
    """스코어러 집계 — 답변 1건 단위."""
    n = len(checks)
    by: dict[str, int] = {"ok": 0, "article_missing": 0,
                          "document_missing": 0, "unattributed": 0}
    for c in checks:
        by[c.verdict] += 1
    verified_rate = (by["ok"] / n) if n else 0.0
    return {
        "total": n, **by,
        "verified_rate": round(verified_rate, 4),
        # 품질 서열 1위 위반(비실재 인용) 존재 여부 — 답변 단위 치명 플래그
        "has_fabrication": (by["article_missing"] + by["document_missing"]) > 0,
    }
