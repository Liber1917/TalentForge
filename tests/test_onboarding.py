"""M10 首启引导状态端点测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.storage.db import init_db, insert_decision, insert_event


def _client(tmp_path: Path, monkeypatch: Any) -> TestClient:
    from talentforge.api import common

    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials", lambda: ("", "", "")
    )
    # 画像指向不存在的文件 → profile=False
    monkeypatch.setattr(common, "profile_path", lambda: tmp_path / "absent.json")
    return TestClient(create_app(conn=init_db(":memory:")))


def test_fresh_state_all_false(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(tmp_path, monkeypatch)
    data = client.get("/api/onboarding/status").json()
    assert data["ok"] is True
    assert data["profile"] is False
    assert data["extension"] is False
    assert data["llm"] is False
    assert data["decisions"] is False


def test_extension_true_when_jobs_or_events_exist(tmp_path: Path, monkeypatch: Any) -> None:
    from talentforge.api.app import create_app as ca
    from talentforge.storage.db import DEFAULT_DB_PATH

    # 用带数据的内存库
    conn = init_db(":memory:", check_same_thread=False)
    insert_event(conn, "e1", "job_view", "u", "t", "boss", "{}", "{}", "2026-08-26T00:00:00")
    client = TestClient(ca(conn=conn))
    data = client.get("/api/onboarding/status").json()
    assert data["extension"] is True


def test_decisions_true_when_history_exists(tmp_path: Path, monkeypatch: Any) -> None:
    from talentforge.api.app import create_app as ca

    conn = init_db(":memory:", check_same_thread=False)
    insert_decision(conn, "u1", "boss", "t", "A", "hold", "r", [], [], None)
    client = TestClient(ca(conn=conn))
    data = client.get("/api/onboarding/status").json()
    assert data["decisions"] is True
