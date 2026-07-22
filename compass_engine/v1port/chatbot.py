"""v1port shim — nexus_critical_classifier 가 lazy import 하는
chatbot._gen_claude 만 v1 시그니처 그대로 재현 (v1 chatbot.py:805).

(text, thinking, model_id) 반환. 모델은 v1 과 동일한
env NEXUS_CLAUDE_MODEL (기본 claude-opus-4-7). ANTHROPIC_API_KEY 부재/실패는
raise — classifier 쪽 try/except 가 v1 과 동일하게 fail-open 처리한다.
"""
from __future__ import annotations

import os


def _gen_claude(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str]:
    import anthropic
    model = os.environ.get("NEXUS_CLAUDE_MODEL", "claude-opus-4-7")
    cli = anthropic.Anthropic()
    msg = cli.messages.create(
        model=model, max_tokens=1024, system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return text, "", model
