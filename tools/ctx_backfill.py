"""contextual retrieval 백필 — nexus_chunks 628청크에 ctx_prefix + ctx_embedding 기록.

ADR-8 완화 지시 3. 쓰기는 **ctx_prefix / ctx_embedding 두 컬럼만** —
v1 이 읽는 embedding·text·auto_* 등은 절대 건드리지 않는다
(v1=기존 embedding, v2=ctx_embedding → 같은 테이블 무간섭 공존).

선행: db/additive/20260721_ctx_columns_and_v4.sql 이 v1 프로젝트에 적용돼 있어야 함.

사용법:
    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... GEMINI_API_KEY=... \
        python tools/ctx_backfill.py [--dry-run] [--limit N] [--force]

동작:
- 문서(active)별로 청크를 chunk_idx 순 로드.
- 청크마다 LLM 1콜: 문서 제목+이웃 요지 기반 1~2문장 맥락(ctx_prefix) 생성.
- ctx_embedding = embed(ctx_prefix + "\n" + text), RETRIEVAL_DOCUMENT, 768.
- 기본은 ctx_embedding IS NULL 행만 처리 (재실행 = 이어하기). --force 로 전체.
- 실패 청크는 건너뛰고 stderr 기록 — 마지막에 실패 목록 요약 (silent fail 금지).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

CTX_MODEL = os.environ.get("CTX_MODEL", "gemini-3.1-flash-lite")
EMBED_MODEL = "gemini-embedding-001"
SLEEP_S = float(os.environ.get("CTX_SLEEP_S", "0.35"))   # rate-limit 완충

_PROMPT = """다음은 사내 규정 문서 "{title}" 의 한 청크입니다.
이 청크가 문서 어디쯤의 무슨 내용인지 검색에 도움이 되도록 1~2문장으로
한국어 맥락을 써 주세요. 조항 번호가 보이면 포함하세요. 맥락 문장만 출력.

[청크]
{text}"""


def main() -> int:
    ap = argparse.ArgumentParser(description="ctx_prefix/ctx_embedding 백필")
    ap.add_argument("--dry-run", action="store_true", help="쓰기 없이 대상 개수만")
    ap.add_argument("--limit", type=int, default=0, help="처리 상한 (0=전체)")
    ap.add_argument("--force", action="store_true",
                    help="ctx_embedding 이 이미 있는 행도 재생성")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL") or ""
    key = os.environ.get("SUPABASE_SERVICE_KEY") or ""
    gem = os.environ.get("GEMINI_API_KEY") or ""
    if not (url and key and gem):
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY / GEMINI_API_KEY 필요",
              file=sys.stderr)
        return 2
    try:
        from supabase import create_client
        from google import genai
    except ImportError as e:
        print(f"ERROR: 의존성 미설치 ({e}) — pip install supabase google-genai",
              file=sys.stderr)
        return 2

    sb = create_client(url, key)
    cli = genai.Client(api_key=gem)

    docs = (sb.table("nexus_documents").select("id, title")
            .eq("status", "active").execute().data or [])
    title_by_id = {d["id"]: d.get("title") or "" for d in docs}

    q = sb.table("nexus_chunks").select("id, document_id, chunk_idx, text")
    if not args.force:
        q = q.is_("ctx_embedding", "null")
    rows = q.order("document_id").order("chunk_idx").execute().data or []
    rows = [r for r in rows if r.get("document_id") in title_by_id]
    if args.limit:
        rows = rows[: args.limit]
    print(f"대상 청크: {len(rows)}건 (active 문서 {len(title_by_id)}개, "
          f"{'force' if args.force else 'ctx_embedding IS NULL 만'})")
    if args.dry_run:
        return 0

    done, failed = 0, []
    for i, r in enumerate(rows, 1):
        cid = r["id"]
        try:
            prompt = _PROMPT.format(
                title=title_by_id[r["document_id"]], text=(r.get("text") or "")[:4000],
            )
            res = cli.models.generate_content(
                model=CTX_MODEL, contents=prompt,
                config={"temperature": 0.0, "max_output_tokens": 160},
            )
            prefix = (getattr(res, "text", "") or "").strip()[:500]
            if not prefix:
                raise RuntimeError("빈 ctx_prefix")
            emb = cli.models.embed_content(
                model=EMBED_MODEL, contents=f"{prefix}\n{r.get('text') or ''}",
                config={"task_type": "RETRIEVAL_DOCUMENT",
                        "output_dimensionality": 768},
            )
            vec = list(emb.embeddings[0].values)
            # ctx_* 두 컬럼만 update — v1 컬럼 불가침
            sb.table("nexus_chunks").update(
                {"ctx_prefix": prefix, "ctx_embedding": vec}
            ).eq("id", cid).execute()
            done += 1
        except Exception as e:
            failed.append(cid)
            print(f"[ctx_backfill] FAILED chunk={cid}: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
        if i % 25 == 0:
            print(f"  … {i}/{len(rows)} (성공 {done}, 실패 {len(failed)})")
        time.sleep(SLEEP_S)

    print(f"완료: 성공 {done} / 실패 {len(failed)} / 대상 {len(rows)}")
    if failed:
        print(f"실패 chunk id: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
