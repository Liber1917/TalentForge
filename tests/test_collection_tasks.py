"""M11 分级采集测试：policy 分档/配额/冷却 + collection_tasks 原子操作 + 路由契约。

D30 红线编码在 policy 默认表：bilibili/zhihu=manual（行为类平台永不 auto）、
zhipin=assist、lagou/linkedin=blocked（侦察结论）；auto 仅限岗位事实平台。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.sources.collection_policy import (
    DEFAULT_POLICY,
    can_auto,
    load_policy,
    mode_for,
)
from talentforge.storage.db import (
    claim_next_task,
    count_tasks_today,
    enqueue_task,
    init_db,
    platform_in_cooldown,
    report_task,
)


def _client(tmp_path: Path, monkeypatch, policy: dict | None = None) -> TestClient:
    policy_path = tmp_path / "policy.json"
    if policy is not None:
        policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TALENTFORGE_COLLECTION_POLICY", str(policy_path))
    return TestClient(create_app(conn=init_db(":memory:", check_same_thread=False)))


# ---------------- policy 纯函数 ----------------


def test_policy_default_modes_encode_d30_redlines() -> None:
    assert mode_for("zhaopin") == "auto"
    assert mode_for("shixiseng") == "auto"
    assert mode_for("liepin") == "auto"
    assert mode_for("zhipin") == "assist"
    assert mode_for("bilibili") == "manual"
    assert mode_for("zhihu") == "manual"
    assert mode_for("lagou") == "blocked"
    assert mode_for("linkedin") == "blocked"
    assert mode_for("unknown-platform") == "blocked"  # 未知平台默认禁入


def test_can_auto_respects_mode_and_kill_switch() -> None:
    assert can_auto("zhaopin") is True
    assert can_auto("zhipin") is False
    assert can_auto("bilibili") is False
    paused = {"paused": True}
    assert can_auto("zhaopin", paused) is False
    disabled = {"platforms": {"zhaopin": {"enabled": False}}}
    assert can_auto("zhaopin", disabled) is False


def test_policy_override_json(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(
        json.dumps({"paused": True, "platforms": {"zhaopin": {"daily_quota": 5}}}),
        encoding="utf-8",
    )
    state = load_policy(path)
    assert state["paused"] is True
    assert state["platforms"]["zhaopin"]["daily_quota"] == 5
    # 损坏 JSON → 静默回落默认表
    path.write_text("{not-json", encoding="utf-8")
    assert load_policy(path) == {"paused": False, "platforms": DEFAULT_POLICY}


# ---------------- collection_tasks 存储 ----------------


def test_enqueue_dedupes_pending_same_platform_url() -> None:
    conn = init_db(":memory:")
    first = enqueue_task(conn, "shixiseng", "https://www.shixiseng.com/interns?k=python")
    dup = enqueue_task(conn, "shixiseng", "https://www.shixiseng.com/interns?k=python")
    assert first is not None and first > 0
    assert dup is None  # 同平台同 URL 未完成 → 去重拒绝
    other = enqueue_task(conn, "zhaopin", "https://www.shixiseng.com/interns?k=python")
    assert other is not None  # 不同平台不算重复


def test_enqueue_dwell_budget_capped() -> None:
    conn = init_db(":memory:")
    tid = enqueue_task(conn, "zhaopin", "https://www.zhaopin.com/sou/", dwell_ms=120_000)
    row = conn.execute("SELECT dwell_ms FROM collection_tasks WHERE id=?", (tid,)).fetchone()
    assert row["dwell_ms"] <= 30_000


def test_claim_next_is_atomic_and_ordered() -> None:
    conn = init_db(":memory:")
    a = enqueue_task(conn, "shixiseng", "https://a")
    b = enqueue_task(conn, "shixiseng", "https://b")
    t1 = claim_next_task(conn, runner="runner-1")
    t2 = claim_next_task(conn, runner="runner-1")
    assert t1["id"] == a and t2["id"] == b
    assert t1["status"] == "running" and t1["runner"] == "runner-1"
    assert claim_next_task(conn, runner="runner-1") is None


def test_report_task_transitions_and_cooldown() -> None:
    conn = init_db(":memory:")
    tid = enqueue_task(conn, "zhaopin", "https://x")
    claim_next_task(conn, runner="r")
    assert report_task(conn, tid, status="done", inserted=7) is True
    row = conn.execute("SELECT * FROM collection_tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "done" and row["finished_at"]

    # aborted + risk_signal → 平台进入冷却
    tid2 = enqueue_task(conn, "zhaopin", "https://y")
    claim_next_task(conn, runner="r")
    report_task(conn, tid2, status="aborted", risk_signal="captcha")
    assert platform_in_cooldown(conn, "zhaopin", minutes=30) is True
    assert platform_in_cooldown(conn, "shixiseng", minutes=30) is False


def test_count_tasks_today_counts_enqueued() -> None:
    conn = init_db(":memory:")
    enqueue_task(conn, "shixiseng", "https://a")
    enqueue_task(conn, "shixiseng", "https://b")
    enqueue_task(conn, "zhaopin", "https://c")
    assert count_tasks_today(conn, "shixiseng") == 2
    assert count_tasks_today(conn, "zhaopin") == 1


# ---------------- 路由契约 ----------------


def test_visit_enqueues_auto_platform_and_rejects_others(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    r = client.post(
        "/api/tasks/visit",
        json={"platform": "shixiseng", "urls": ["https://www.shixiseng.com/interns?k=python"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["enqueued"] == 1 and body["task_ids"]

    for platform, why in [
        ("bilibili", "manual"),
        ("zhipin", "assist"),
        ("lagou", "blocked"),
        ("linkedin", "blocked"),
    ]:
        r = client.post(
            "/api/tasks/visit", json={"platform": platform, "urls": ["https://x"]}
        )
        assert r.status_code == 403, platform
        assert why in r.json()["detail"] or platform in r.json()["detail"]


def test_visit_quota_and_cooldown_guardrails(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch, policy={"platforms": {"shixiseng": {"daily_quota": 1}}})
    client.post("/api/tasks/visit", json={"platform": "shixiseng", "urls": ["https://a"]})
    r = client.post("/api/tasks/visit", json={"platform": "shixiseng", "urls": ["https://b"]})
    assert r.status_code == 429  # 配额用尽

    # 风控信号 → 冷却 → 再入队 403
    tasks = client.get("/api/tasks", params={"limit": 10}).json()["tasks"]
    tid = tasks[0]["id"]
    client.get("/api/tasks/next", params={"runner": "runner-q"})  # pending → running
    client.post(f"/api/tasks/{tid}/report", json={"status": "aborted", "risk_signal": "captcha"})
    r = client.post("/api/tasks/visit", json={"platform": "shixiseng", "urls": ["https://c"]})
    assert r.status_code == 403


def test_claim_and_report_roundtrip(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    r = client.post(
        "/api/tasks/visit",
        json={"platform": "zhaopin", "urls": ["https://www.zhaopin.com/sou/"], "dwell_ms": 20_000},
    )
    tid = r.json()["task_ids"][0]

    claimed = client.get("/api/tasks/next", params={"runner": "runner-x"})
    assert claimed.status_code == 200
    task = claimed.json()
    assert task["id"] == tid and task["status"] == "running"
    assert task["dwell_ms"] == 20_000

    empty = client.get("/api/tasks/next", params={"runner": "runner-x"})
    assert empty.status_code == 204

    done = client.post(f"/api/tasks/{tid}/report", json={"status": "done", "inserted": 12})
    assert done.status_code == 200 and done.json()["ok"] is True
    listed = client.get("/api/tasks", params={"limit": 5}).json()["tasks"]
    assert listed[0]["status"] == "done"


def test_report_rejects_unknown_status(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/tasks/visit", json={"platform": "zhaopin", "urls": ["https://a"]})
    tid = r.json()["task_ids"][0]
    bad = client.post(f"/api/tasks/{tid}/report", json={"status": "pending"})
    assert bad.status_code == 422


def test_extension_origin_allowed_for_ingest_only(tmp_path: Path, monkeypatch) -> None:
    """M11：chrome-extension:// Origin 仅放行采集摄入端点，其余端点仍 403。"""
    client = _client(tmp_path, monkeypatch)
    ext_origin = {"Origin": "chrome-extension://abc123def456"}
    ingest = client.post(
        "/api/tasks/visit",
        headers=ext_origin,
        json={"platform": "shixiseng", "urls": ["https://www.shixiseng.com/interns?k=E2E"]},
    )
    assert ingest.status_code == 200
    jobs = client.post(
        "/api/jobs/batch", headers=ext_origin, json={"source": "shixiseng", "jobs": []}
    )
    assert jobs.status_code == 200

    assert client.get("/api/health", headers=ext_origin).status_code == 403
    evil = {"Origin": "https://evil.example.com"}
    assert client.get("/api/health", headers=evil).status_code == 403
