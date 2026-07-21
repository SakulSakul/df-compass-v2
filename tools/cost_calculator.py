"""DF COMPASS v2 · 게이트 1 비용 계산기.

gate1-measurement-kit.sql 의 결과 4개 + 현행 단가를 입력하면
CAG-primary vs RAG 월 비용과 G1 판정(3배 상한)을 출력한다.

단가는 반드시 실행 시점의 Gemini 공식 가격표로 갱신할 것 —
아래 기본값은 자리표시자다 (v1 주석의 "1/4"는 RAG 대비가 아니라
동일 long-context 비캐시 대비임에 유의).
"""

# ── 측정값 입력 (SQL 결과) ────────────────────────────────
CORPUS_TOKENS = 284_849  # [M1] tokens_est_high (사규 active 전체) — 2026-07-21 실측
DAILY_QUERIES = 24.1     # [M3] avg_per_day (90일 평균, peak_day 602)
CRITICAL_PCT = 13.0      # [M4] critical_pct (%)
RAG_CTX_TOKENS = 6_809   # [M5] avg_rag_context_tokens (p95 12,335)

# ── 단가 입력 ($ / 1M tokens) — 실행 시점 공식 가격으로 갱신 ──
PRICE_INPUT = 0.30       # 비캐시 입력 단가
PRICE_CACHED = 0.03      # 캐시 적중 입력 단가 — 2026-07 Gemini 공식가 갱신(측정 시점)
PRICE_STORAGE_PER_M_HOUR = 1.00  # explicit cache storage, $/1M tok/hour
CACHE_HOURS_PER_DAY = 12  # 캐시 활성 유지 시간/일 (업무시간만이면 ~10-12)

PROMPT_OVERHEAD = 3_000   # 시스템프롬프트+질문 등 코퍼스 외 입력 토큰/질의
G1_MULTIPLIER = 3.0       # G1 상한: RAG 대비 배수

M = 1_000_000
mo = 30

def usd(x): return f"${x:,.2f}"

# CAG: 질의마다 (코퍼스 캐시분 + 오버헤드 비캐시분), critical은 캐시 우회 가정 없이
# 보수적으로 전 질의 캐시 적중으로 계산하되 storage를 상시 부과
cag_query = (CORPUS_TOKENS * PRICE_CACHED + PROMPT_OVERHEAD * PRICE_INPUT) / M
cag_storage_day = CORPUS_TOKENS / M * PRICE_STORAGE_PER_M_HOUR * CACHE_HOURS_PER_DAY
cag_month = cag_query * DAILY_QUERIES * mo + cag_storage_day * mo

# RAG: 질의마다 top-k 컨텍스트 + 오버헤드 (검색 인프라 비용은 Supabase 고정비로 동일 취급)
rag_query = (RAG_CTX_TOKENS + PROMPT_OVERHEAD) * PRICE_INPUT / M
rag_month = rag_query * DAILY_QUERIES * mo

print(f"코퍼스           : {CORPUS_TOKENS:,} tok")
print(f"일 질의량         : {DAILY_QUERIES:,.0f}  (critical {CRITICAL_PCT}%)")
print(f"CAG  질의당      : {usd(cag_query)}   저장/일: {usd(cag_storage_day)}")
print(f"RAG  질의당      : {usd(rag_query)}")
print(f"월 비용  CAG {usd(cag_month)}  vs  RAG {usd(rag_month)}")
if rag_month > 0:
    ratio = cag_month / rag_month
    verdict = "통과 — CAG-primary 진행" if ratio <= G1_MULTIPLIER else "미통과 — RAG 유지"
    print(f"배수 {ratio:.1f}x  →  G1({G1_MULTIPLIER}x 상한) {verdict}")
if CRITICAL_PCT >= 30:
    print("⚠ critical 비중 30%+ — CAG 실효 적용률 재평가 필요 (Kill criteria)")
