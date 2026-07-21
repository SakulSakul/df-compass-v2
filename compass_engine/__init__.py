"""compass_engine — DF COMPASS v2 엔진 패키지 (Phase 0: 계약 뼈대만).

DESIGN.md §2 엔진 계약. UI(Streamlit)·eval CLI·(미래 MCP)가 동일 진입점을 호출한다.
Phase 0 범위: 스테이지 typed 입출력 + trace 레코드 계약 + retrieve 교체형 인터페이스.
구현(검색·합성·검증 로직)은 Phase 1.
"""
from compass_engine.articles import ArticleRef, extract_article_refs, parse_article_ref
