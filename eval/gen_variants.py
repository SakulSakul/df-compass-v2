"""변형 문항 생성기 (지시서 §5 ★) — 1회 실행 → eval/variants.yaml 커밋.

- 대상: golden 52 중 critical 8·negative 6 제외 38문항, 문항당 변형 1개.
- 결정론화: 고정 시드(SEED)·고정 프롬프트·temperature 0. LLM 특성상 완전
  재현이 보장되진 않으므로 **커밋된 variants.yaml 이 정본** — 러닝은 이 파일만
  읽고 재생성하지 않는다 (compare_v1v2.load_variants).
- Δ 판정·비교 판정은 golden 52 원본 한정 (★). 변형은 탐색·참고 지표.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from eval.runner import load_fixtures  # noqa: E402

SEED = 20260728
MODEL = "gemini-3.6-flash"
EXCLUDED = ("critical", "negative")
PROMPT = ("다음은 회사 사규 챗봇에 들어온 질문이다. 의미·대상 규정·질문 의도를 "
          "그대로 보존하면서 표현만 자연스럽게 바꾼 한국어 변형 질문 1개를 "
          "만들어라. 원문에 없는 조건이나 대상을 추가하지 말 것. "
          "출력은 변형 질문 한 줄만.\n\n원문: {q}")


def main() -> int:
    from google import genai
    cli = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    entries = [e for e in load_fixtures(_ROOT / "eval" / "golden.yaml")
               if e.get("category") not in EXCLUDED]
    lines = [
        "# eval/variants.yaml — 변형 문항 트랙 (지시서 §5, 생성 후 동결·커밋)",
        f"# 생성기: eval/gen_variants.py  model={MODEL}  seed={SEED}  temp=0.0",
        "# 대상: critical·negative 제외 38문항 × 1변형. 이 파일이 정본 —",
        "# 러닝은 재생성 없이 이 파일만 읽는다. 판정은 golden 52 원본 한정.",
    ]
    for i, e in enumerate(entries, 1):
        res = cli.models.generate_content(
            model=MODEL, contents=PROMPT.format(q=e["question"]),
            config={"temperature": 0.0, "seed": SEED,
                    "max_output_tokens": 1024,
                    "thinking_config": {"thinking_level": "minimal"}},
        )
        var = (getattr(res, "text", "") or "").strip().replace("\n", " ")
        if not var:
            print(f"[gen_variants] {e['id']} EMPTY — 중단", file=sys.stderr)
            return 1
        lines.append(f'- {{id: {e["id"]}v1, base_id: {e["id"]}, '
                     f'question: "{var.replace(chr(34), chr(39))}"}}')
        print(f"… {i}/{len(entries)} {e['id']}: {var}", flush=True)
    out = _ROOT / "eval" / "variants.yaml"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
