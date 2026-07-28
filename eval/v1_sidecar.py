"""v1 로컬 사이드카 어댑터 — v1(nexus_ai) retrieve→합성 경로를 직접 구동.

지시서 §1 (심의 확정 ★):
- 배포 v1 앱 호출 전면 금지 → 로컬 v1 코드를 sys.path 주입 + 함수 호출로만 실행.
- v1 레포 파일 수정 0: sys.dont_write_bytecode 로 __pycache__ 생성까지 차단.
- 몽키패치 금지: v1 모듈 속성을 일절 바꾸지 않는다. DB 쓰기 차단은 v1 이
  인자로 받는 supabase 클라이언트를 GuardedSupabase 로 감싸 주입하는
  의존성 주입 방식 — v1 의 query_logs insert 는 전부 try/except 로 감싸져
  있어(chatbot.py:1652-1662 등) 차단 예외는 v1 자체의 실패 처리로 흡수되고
  검색·합성 동작은 불변이다. 우회 지점은 GuardLog 에 전수 기록.
- 모델·env 는 운영 v1 동일: NEXUS_CHAT_MODEL=gemini-3.6-flash (2026-07-22
  운영 교체 확정분). 운영 feature flag(ENABLE_*) 는 Streamlit secrets 라
  로컬에서 실값 확인 불가 → v1 코드 기본값(전부 false) 사용, 결과에 명시.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

V1_ROOT = Path(os.environ.get("V1_REPO_PATH", "/home/user/nexus_ai"))

# 운영 v1 과 동일하게 맞추는 env (이미 설정돼 있으면 존중)
V1_ENV_DEFAULTS = {
    "NEXUS_CHAT_MODEL": "gemini-3.6-flash",
    "NEXUS_CHAT_PROVIDER": "gemini",
}


class WriteBlocked(RuntimeError):
    """사이드카 가드가 차단한 DB 쓰기 시도 (ADR-8 / 지시서 §1)."""


class GuardLog:
    """차단·통과 접근 전수 기록 — 스모크 ⑤ 'DB 쓰기 0' 증적."""

    def __init__(self) -> None:
        self.blocked: list[dict] = []
        self.rpc_calls: Counter = Counter()
        self.table_reads: Counter = Counter()

    def summary(self) -> dict:
        return {
            "blocked_writes": self.blocked,
            "blocked_write_count": len(self.blocked),
            "rpc_calls": dict(self.rpc_calls),
            "table_reads": dict(self.table_reads),
        }


class _GuardedTable:
    """table() 빌더 프록시 — 쓰기 동사 4종만 차단, 나머지는 passthrough.

    supabase-py 의 쓰기는 반드시 insert/update/upsert/delete 동사로 시작하므로
    첫 동사 차단으로 충분하다 (.select().eq()... 체인은 읽기 전용).
    """

    _WRITE_VERBS = ("insert", "update", "upsert", "delete")

    def __init__(self, real: Any, name: str, log: GuardLog) -> None:
        self._real = real
        self._name = name
        self._log = log

    def _block(self, verb: str):
        def _raise(*_a: Any, **_k: Any) -> Any:
            self._log.blocked.append({"table": self._name, "verb": verb})
            raise WriteBlocked(
                f"[v1_sidecar] blocked {verb} on {self._name} (ADR-8)")
        return _raise

    def __getattr__(self, item: str) -> Any:
        if item in self._WRITE_VERBS:
            return self._block(item)
        return getattr(self._real, item)


class GuardedSupabase:
    """v1 에 주입하는 SELECT/RPC 전용 클라이언트 래퍼."""

    def __init__(self, real: Any, log: GuardLog | None = None) -> None:
        self._real = real
        self.guard_log = log or GuardLog()

    def table(self, name: str) -> _GuardedTable:
        self.guard_log.table_reads[name] += 1
        return _GuardedTable(self._real.table(name), name, self.guard_log)

    def rpc(self, name: str, params: Any = None) -> Any:
        self.guard_log.rpc_calls[name] += 1
        if params is None:
            return self._real.rpc(name)
        return self._real.rpc(name, params)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._real, item)


def ensure_v1_on_path() -> Path:
    """v1 레포를 sys.path **끝**에 추가 (+bytecode 금지 + 운영 env 기본값).

    끝에 붙이는 이유: v1 레포에도 최상위 `eval/` 패키지가 있어, 앞에 넣으면
    v2 의 eval.* import 가 v1 쪽으로 새는 충돌이 난다. v2 root 가 항상 우선.
    """
    sys.dont_write_bytecode = True  # v1 레포에 __pycache__ 생성 금지
    for k, v in V1_ENV_DEFAULTS.items():
        os.environ.setdefault(k, v)
    p = str(V1_ROOT)
    if not V1_ROOT.exists():
        raise FileNotFoundError(f"v1 repo not found: {p} (V1_REPO_PATH env)")
    if p not in sys.path:
        sys.path.append(p)
    return V1_ROOT


def load_v1_chatbot() -> Any:
    """v1 core.chatbot 모듈 로드 + 실경로 증적 검증 (스모크 ④)."""
    ensure_v1_on_path()
    from core import chatbot  # v1 repo 의 core 패키지
    mod_path = Path(chatbot.__file__).resolve()
    if V1_ROOT.resolve() not in mod_path.parents:
        raise RuntimeError(
            f"[v1_sidecar] core.chatbot resolved outside v1 repo: {mod_path}")
    return chatbot


def run_env_snapshot() -> dict:
    """결과 JSON 에 기록할 v1 실행 구성 (지시서 §1: model id·env 명시)."""
    keys = sorted(k for k in os.environ
                  if k.startswith("NEXUS_") or k.startswith("ENABLE_"))
    return {
        "v1_repo": str(V1_ROOT),
        "chat_model": os.environ.get("NEXUS_CHAT_MODEL"),
        "chat_provider": os.environ.get("NEXUS_CHAT_PROVIDER"),
        "chat_fallback": os.environ.get("NEXUS_CHAT_FALLBACK", "(unset=없음)"),
        "env_vars": {k: os.environ[k] for k in keys},
        "flags_note": ("운영 Streamlit secrets 의 ENABLE_* 실값은 로컬 확인 불가 — "
                       "미설정 키는 v1 코드 기본값(false) 적용"),
    }


def run_v1(chatbot: Any, sb: GuardedSupabase, question: str) -> dict:
    """v1 ask() 1문항 실행 → 비교 러너용 레코드."""
    t0 = time.perf_counter()
    ans = chatbot.ask(sb, question=question, category=None)
    total_s = time.perf_counter() - t0
    return {
        "answer": ans.text,
        "is_critical": ans.is_critical,
        "critical_kind": ans.critical_kind,
        "confidence": ans.confidence,
        "elapsed_total_s": round(total_s, 3),
        "elapsed_ask_s": round(ans.elapsed, 3),
        "context_docs": sorted({c.get("doc_title") for c in (ans.contexts or [])
                                if c.get("doc_title")}),
        "module_path": str(Path(chatbot.__file__).resolve()),
    }
