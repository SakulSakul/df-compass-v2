"""v1 사이드카 가드 오프라인 테스트 — 쓰기 4동사 차단·읽기/RPC passthrough."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.v1_sidecar import (  # noqa: E402
    GuardedSupabase, WriteBlocked, ensure_v1_on_path)
import eval.v1_sidecar as sidecar  # noqa: E402


class _FakeBuilder:
    def __init__(self):
        self.calls = []

    def select(self, *a, **k):
        self.calls.append(("select", a))
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return type("R", (), {"data": [{"ok": True}]})()

    def insert(self, *a, **k):
        raise AssertionError("real insert must never be reached")

    def update(self, *a, **k):
        raise AssertionError("real update must never be reached")

    def upsert(self, *a, **k):
        raise AssertionError("real upsert must never be reached")

    def delete(self, *a, **k):
        raise AssertionError("real delete must never be reached")


class _FakeClient:
    def __init__(self):
        self.builder = _FakeBuilder()
        self.rpc_calls = []

    def table(self, name):
        return self.builder

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params))
        return self.builder


def test_guard_blocks_all_write_verbs():
    g = GuardedSupabase(_FakeClient())
    for verb in ("insert", "update", "upsert", "delete"):
        with pytest.raises(WriteBlocked):
            getattr(g.table("query_logs"), verb)({"x": 1})
    log = g.guard_log.summary()
    assert log["blocked_write_count"] == 4
    assert all(b["table"] == "query_logs" for b in log["blocked_writes"])


def test_guard_passes_reads_and_rpc():
    real = _FakeClient()
    g = GuardedSupabase(real)
    rows = g.table("nexus_documents").select("id").eq("status", "active").execute()
    assert rows.data == [{"ok": True}]
    g.rpc("nexus_hybrid_search_v4_ctx", {"q": "x"}).execute()
    assert real.rpc_calls == [("nexus_hybrid_search_v4_ctx", {"q": "x"})]
    log = g.guard_log.summary()
    assert log["blocked_write_count"] == 0
    assert log["table_reads"] == {"nexus_documents": 1}
    assert log["rpc_calls"] == {"nexus_hybrid_search_v4_ctx": 1}


def test_ensure_v1_on_path_appends_last(tmp_path, monkeypatch):
    monkeypatch.setattr(sidecar, "V1_ROOT", tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    ensure_v1_on_path()
    assert sys.path[-1] == str(tmp_path)      # v2 root 우선 (eval/ 충돌 방지)
    assert sys.dont_write_bytecode is True    # v1 레포 __pycache__ 생성 금지


def test_ensure_v1_on_path_missing_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(sidecar, "V1_ROOT", tmp_path / "nope")
    with pytest.raises(FileNotFoundError):
        ensure_v1_on_path()
