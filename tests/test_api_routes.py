"""M3 Task 7 真端点测试：chat/claims/jobs/report/profile 五组路由 + FakeLLM 注入。

参照 test_api_app.py 注入方式：create_app(conn=:memory:, llm=FakeLLM)；
画像持久化用 TALENTFORGE_PROFILE_PATH 指向临时文件，避免改动 docs/demo/profile.json。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.api.schemas import ChatTurn
from talentforge.domain.job import Job
from talentforge.storage.db import init_db, upsert_job

VALID_MATCH_JSON = (
    "```json\n"
    '{"market_fit": "high", "growth_fit": "high", '
    '"reasoning": ["技能与岗位要求匹配"], "matched": ["Python"], "missing": []}\n'
    "```"
)
CLAIM_JSON = '{"claims": [{"text": "用户对分布式系统/系统设计积累较深", "confidence": 0.7}]}'


class FakeLLM:
    """按 system prompt 路由返回：匹配 JSON / 主张 JSON / 闲聊文本，记录调用。"""

    def __init__(self) -> None:
        self.systems: list[str] = []

    async def chat(self, system: str, user: str) -> str:
        self.systems.append(system)
        if "匹配评估器" in system:
            return VALID_MATCH_JSON
        if "画像构建器" in system:
            return CLAIM_JSON
        return "我在听，你继续说说你的情况。"


class FailingLLM:
    """模拟 LLM 未配置/失败：chat 直接抛错，验证降级不 500。"""

    async def chat(self, system: str, user: str) -> str:
        raise RuntimeError("LLM 未配置")


def _job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = dict(
        source="boss",
        title="Python 后端工程师",
        company="星辰科技",
        location="深圳·南山",
        url="https://www.zhipin.com/job_detail/api_1.html",
        description="负责分布式系统开发",
        risk_keys=[],
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def _profile_payload() -> dict:
    demo = Path(__file__).resolve().parents[1] / "docs" / "demo" / "profile.json"
    return json.loads(demo.read_text(encoding="utf-8"))


def _make_client(monkeypatch: Any, tmp_path: Path) -> tuple[TestClient, Any]:
    """临时画像文件 + 内存库 + FakeLLM 的应用；返回 (client, conn)。"""
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_profile_payload(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(profile_path))
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn, llm=FakeLLM())), conn


def _decision_cards(turn: dict) -> list[dict]:
    return [c for c in turn.get("cards", []) if c.get("type") == "decision"]


def _url(name: str) -> str:
    return f"https://www.zhipin.com/job_detail/{name}.html"


def test_get_chat_turns_returns_valid_contract(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.get("/api/chat/turns")
    assert response.status_code == 200
    turns = response.json()
    assert isinstance(turns, list)
    for turn in turns:
        parsed = ChatTurn.model_validate(turn)
        assert parsed.role in ("user", "assistant")
        for card in parsed.cards:
            assert card.type in {"decision", "claim", "risk", "reflective"}


def test_chat_decision_returns_decision_cards(monkeypatch: Any, tmp_path: Path) -> None:
    client, conn = _make_client(monkeypatch, tmp_path)
    upsert_job(conn, _job(id="d1", url=_url("d_1"), risk_keys=[]))
    upsert_job(conn, _job(id="d2", url=_url("d_2"), risk_keys=["996"]))

    response = client.post("/api/chat/turns", json={"text": "帮我看看深圳的岗位"})
    assert response.status_code == 200
    turn = response.json()
    assert turn["role"] == "assistant"
    cards = _decision_cards(turn)
    assert cards, "决策意图应产出 DecisionCard"
    for card in cards:
        assert card["verdict"] in ("apply", "hold", "skip")
        assert card["job"]["title"]
        assert "risk_hits" in card
        assert "reason" in card
        assert "evidence" in card


def test_chat_free_dialogue_returns_assistant_turn(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.post("/api/chat/turns", json={"text": "我想聊聊我的简历"})
    assert response.status_code == 200
    turn = response.json()
    assert turn["role"] == "assistant"
    assert turn["text"]
    claim_cards = [c for c in turn["cards"] if c.get("type") == "claim"]
    assert claim_cards, "提及自身情况应沉淀 trial claim 卡"
    assert claim_cards[0]["state"] == "trial"


def test_chat_degraded_when_llm_fails(monkeypatch: Any, tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_profile_payload(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(profile_path))
    conn = init_db(":memory:", check_same_thread=False)
    client = TestClient(create_app(conn=conn, llm=FailingLLM()))
    response = client.post("/api/chat/turns", json={"text": "聊聊我的简历"})
    assert response.status_code == 200
    turn = response.json()
    assert turn["role"] == "assistant"
    assert turn["text"]


def test_reflective_reply_creates_claim(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    answer = "996 如果给足对价和时间弹性我可以谈"
    response = client.post(
        "/api/chat/turns",
        json={"text": answer, "reply_to": "你上次说 996 是硬边界，现在怎么权衡？"},
    )
    assert response.status_code == 200
    turn = response.json()
    claim_cards = [c for c in turn["cards"] if c.get("type") == "claim"]
    assert claim_cards
    assert claim_cards[0]["state"] == "trial"
    assert claim_cards[0]["text"] == answer
    data = client.get("/api/profile").json()
    assert answer in [c["text"] for c in data["narrative_claims"]]


def test_chat_history_grows(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    before = client.get("/api/chat/turns").json()
    client.post("/api/chat/turns", json={"text": "你好啊"})
    after = client.get("/api/chat/turns").json()
    assert len(after) == len(before) + 2


def test_claim_confirm_then_reject(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    profile_data = client.get("/api/profile").json()
    trial = [c for c in profile_data["narrative_claims"] if c["state"] == "trial"]
    assert trial

    claim_id = trial[0]["claim_id"]
    response = client.post(f"/api/claims/{claim_id}/confirm")
    assert response.status_code == 200
    card = response.json()
    assert card["state"] == "active"
    assert card["evidence_count"] == trial[0]["evidence_count"] + 1
    assert card["claim_id"] == claim_id

    updated = client.get("/api/profile").json()
    updated_claim = next(c for c in updated["narrative_claims"] if c["claim_id"] == claim_id)
    assert updated_claim["state"] == "active"

    next_trial = [c for c in updated["narrative_claims"] if c["state"] == "trial"][0]
    reject = client.post(f"/api/claims/{next_trial['claim_id']}/reject")
    assert reject.status_code == 200
    assert reject.json()["state"] == "archived"


def test_claim_missing_returns_404(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.post("/api/claims/claim-nope/confirm")
    assert response.status_code == 404


def test_jobs_empty_returns_list(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert response.json() == []


def test_jobs_contract_and_filters(monkeypatch: Any, tmp_path: Path) -> None:
    client, conn = _make_client(monkeypatch, tmp_path)
    contract_keys = {
        "title", "company", "location", "salary", "url",
        "verdict", "reason", "risk_hits", "gap", "remediation", "evidence",
    }
    upsert_job(conn, _job(id="j1", url=_url("a"), title="Python 后端", risk_keys=[]))
    upsert_job(
        conn,
        _job(id="j2", url=_url("b"), title="Java 后端", location="广州", risk_keys=["996"]),
    )
    upsert_job(
        conn,
        _job(id="j3", url=_url("c"), title="Go 后端", location="深圳·福田", risk_keys=["单休"]),
    )

    items = client.get("/api/jobs").json()
    assert len(items) == 3
    for item in items:
        assert contract_keys <= set(item)
    by_url = {item["url"]: item for item in items}
    assert by_url[_url("a")]["verdict"] == "apply"
    assert by_url[_url("b")]["verdict"] == "skip"
    assert by_url[_url("c")]["verdict"] == "hold"

    shenzhen = client.get("/api/jobs", params={"city": "深圳"}).json()
    assert len(shenzhen) == 2
    applies = client.get("/api/jobs", params={"verdict": "apply"}).json()
    assert len(applies) == 1
    q_go = client.get("/api/jobs", params={"q": "Go"}).json()
    assert len(q_go) == 1
    assert q_go[0]["title"] == "Go 后端"


def test_report_run_and_status(monkeypatch: Any, tmp_path: Path) -> None:
    client, conn = _make_client(monkeypatch, tmp_path)
    upsert_job(conn, _job(id="r1", url=_url("r1"), risk_keys=[]))
    upsert_job(conn, _job(id="r2", url=_url("r2"), risk_keys=[]))

    response = client.post("/api/report/run", json={"query": "后端", "city": "深圳", "limit": 10})
    assert response.status_code == 200
    assert response.json()["state"] == "running"

    status: dict[str, Any] | None = None
    for _ in range(200):
        status = client.get("/api/report/status").json()
        if status["state"] in ("done", "failed"):
            break
        time.sleep(0.01)
    assert status is not None
    assert status["state"] == "done", status
    assert status["summary"]["n_jobs"] == 2
    assert status["summary"]["n_apply"] == 2
    assert len(status["items"]) == 2


def test_profile_contract(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    data = client.get("/api/profile").json()
    assert {"identity", "values", "deep_drives"} <= set(data["narrative"])
    assert "utility_preferences" in data
    assert "structural_position" in data
    claims = data["narrative_claims"]
    assert claims
    claim_keys = {"claim_id", "text", "state", "evidence_count", "sources", "confidence"}
    for claim in claims:
        assert claim_keys <= set(claim)
        assert claim["state"] in ("trial", "active", "archived")


def test_profile_export(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.get("/api/profile/export")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "narrative_claims" in data
    assert "attachment" in response.headers.get("content-disposition", "")


def test_resume_review_json_path(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    resume = tmp_path / "resume.txt"
    resume.write_text("张三\n3 年经验\n负责分布式系统开发", encoding="utf-8")
    response = client.post("/api/profile/resume-review", json={"resume_file": str(resume)})
    assert response.status_code == 200
    data = response.json()
    assert data["file"] == "resume.txt"
    fields = {item["field"]: item["extracted"] for item in data["items"]}
    assert fields["years_experience"] == "3 年"
    assert fields["full_text"].startswith("张三")


def test_resume_review_multipart(monkeypatch: Any, tmp_path: Path) -> None:
    client, _ = _make_client(monkeypatch, tmp_path)
    response = client.post(
        "/api/profile/resume-review",
        files={"file": ("resume.md", "# 李四\n5 年经验\nGo 后端".encode(), "text/markdown")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["file"] == "resume.md"
    fields = {item["field"]: item["extracted"] for item in data["items"]}
    assert fields["years_experience"] == "5 年"
    assert "Go" in fields["skills"]
