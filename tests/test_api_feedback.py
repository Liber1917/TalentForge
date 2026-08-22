"""M4 Task 2 反馈路由测试：POST 回流管线联调（幂等/段位/兜底）+ GET events/summary。

注入方式（参照 test_api_sources._make_client）：
- TALENTFORGE_PROFILE_PATH → tmp profile.json（最小构造：薪资 ordering + trial claim）
- feedback.store.FEEDBACK_LOG_PATH → tmp feedback_log.json（路由经 feedback_store 模块引用）
- conn = init_db(":memory:")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange
from talentforge.feedback import store as feedback_store
from talentforge.storage.db import init_db, upsert_job

JOB_URL = "https://www.zhipin.com/job_detail/fb_1.html"
ORDERING = ["40万以上", "30-40万", "20-30万"]
CLAIM_TEXT = "对高并发后端服务有实战积累"


def _job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = dict(
        source="boss",
        title="Python 后端工程师",
        company="星辰科技",
        location="深圳·南山",
        url=JOB_URL,
        description="负责分布式系统开发",
        salary=SalaryRange(min_annual=300000, max_annual=350000),
        risk_keys=[],
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def _profile_payload() -> dict:
    return {
        "name": "张三",
        "utility_preferences": {
            "薪资": {"attribute": "薪资", "ordering": ORDERING, "evidence": []}
        },
        "narrative_claims": [
            {"text": CLAIM_TEXT, "state": "trial", "evidence_count": 0, "confidence": 0.7}
        ],
    }


def _make_client(monkeypatch: Any, tmp_path: Path, *, with_profile: bool = True) -> TestClient:
    """tmp 画像 + tmp 反馈日志 + 内存库；with_profile=False 模拟画像文件缺失。"""
    profile_path = tmp_path / "profile.json"
    if with_profile:
        profile_path.write_text(
            json.dumps(_profile_payload(), ensure_ascii=False), encoding="utf-8"
        )
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(profile_path))
    monkeypatch.setattr(feedback_store, "FEEDBACK_LOG_PATH", tmp_path / "feedback_log.json")
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn))


def _event_body(**overrides: Any) -> dict:
    defaults: dict[str, Any] = dict(
        job_id=JOB_URL,
        job_title="Python 后端工程师",
        decision_verdict="apply",
        action="decided",
        at="2026-08-22T10:00:00Z",
    )
    defaults.update(overrides)
    return defaults


def _salary_pref(tmp_path: Path) -> dict:
    data = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    return data["utility_preferences"]["薪资"]


# ---------- POST /api/feedback/events：回流管线联调 ----------


def test_post_decided_apply_lands_salary_evidence(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    upsert_job(client.app.state.conn, _job())

    response = client.post("/api/feedback/events", json=_event_body())
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event"]["job_id"] == JOB_URL
    assert data["event"]["decision_verdict"] == "apply"
    assert any(c.startswith("evidence +1") for c in data["preference_changes"])

    pref = _salary_pref(tmp_path)
    assert pref["ordering"] == ORDERING  # decided 不动序
    assert len(pref["evidence"]) == 1
    assert pref["evidence"][0].startswith("2026-08-22 apply")


def test_post_idempotent_same_job_and_action_updates_not_duplicates(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    upsert_job(client.app.state.conn, _job())

    assert client.post("/api/feedback/events", json=_event_body()).status_code == 200
    second = client.post(
        "/api/feedback/events", json=_event_body(decision_verdict="hold")
    )
    assert second.status_code == 200
    assert second.json()["event"]["decision_verdict"] == "hold"

    events = client.get("/api/feedback/events").json()["events"]
    assert len(events) == 1
    assert events[0]["decision_verdict"] == "hold"


def test_post_outcome_offer_moves_tier_up(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    upsert_job(client.app.state.conn, _job())

    response = client.post(
        "/api/feedback/events",
        json=_event_body(action="outcome", outcome="offer"),
    )
    assert response.status_code == 200
    changes = response.json()["preference_changes"]
    assert "salary ordering: '30-40万' +1 位（offer）" in changes
    assert _salary_pref(tmp_path)["ordering"] == ["30-40万", "40万以上", "20-30万"]


def test_post_unknown_job_skips_preference_rules_without_500(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/feedback/events",
        json=_event_body(job_id="https://example.com/missing"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["preference_changes"] == []
    assert _salary_pref(tmp_path)["evidence"] == []


def test_post_missing_profile_file_falls_back_to_empty_profile(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, with_profile=False)
    upsert_job(client.app.state.conn, _job())

    response = client.post("/api/feedback/events", json=_event_body())
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["preference_changes"] == []
    saved = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert saved["name"] == ""
    assert saved["utility_preferences"] == {}


def test_post_narrative_revision_via_dialogue_note(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    upsert_job(client.app.state.conn, _job())

    response = client.post(
        "/api/feedback/events",
        json=_event_body(dialogue_note="面试聊到我对高并发后端服务很熟"),
    )
    assert response.status_code == 200
    changes = response.json()["preference_changes"]
    assert any(c.startswith("叙事主张证据 +1") for c in changes)
    data = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert data["narrative_claims"][0]["evidence_count"] == 1


def test_post_invalid_body_returns_422(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    assert client.post("/api/feedback/events", json={"job_id": "x"}).status_code == 422


# ---------- GET /api/feedback/events ----------


def test_get_events_desc_order_and_limit(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    for day, job_id in [(20, "a"), (22, "b"), (21, "c")]:
        body = _event_body(job_id=job_id, at=f"2026-08-{day:02d}T10:00:00Z")
        assert client.post("/api/feedback/events", json=body).status_code == 200

    events = client.get("/api/feedback/events", params={"limit": 50}).json()["events"]
    assert [e["job_id"] for e in events] == ["b", "c", "a"]

    limited = client.get("/api/feedback/events", params={"limit": 2}).json()["events"]
    assert [e["job_id"] for e in limited] == ["b", "c"]


# ---------- GET /api/feedback/summary ----------


def test_get_summary_counts(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    posts = [
        _event_body(job_id="a", decision_verdict="apply"),
        _event_body(job_id="b", decision_verdict="hold"),
        _event_body(job_id="c", decision_verdict="skip"),
        _event_body(job_id="a", action="outcome", outcome="offer"),
    ]
    for body in posts:
        assert client.post("/api/feedback/events", json=body).status_code == 200

    summary = client.get("/api/feedback/summary").json()["summary"]
    assert summary == {
        "n_decided": 3,
        "n_apply": 1,
        "n_hold": 1,
        "n_skip": 1,
        "n_outcome": 1,
    }
