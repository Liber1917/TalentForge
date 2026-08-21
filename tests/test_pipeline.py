"""Task 2 事件→画像消费链测试：pipeline 主张生成/累积 + events-ingest/profile-update CLI E2E。"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import talentforge.cli as cli_module
from talentforge.cli import main
from talentforge.domain.profile import Profile
from talentforge.profile.pipeline import EVENT_TO_CLAIM_SYSTEM_PROMPT, ProfileUpdatePipeline
from talentforge.storage.db import init_db, insert_event, list_events

CLAIMS_JSON = (
    '{"claims": ['
    '{"text": "喜欢看分布式系统讲解", "confidence": 0.8, "kind": "preference"},'
    '{"text": "关注后端基础设施方向", "confidence": 0.6, "kind": "narrative"}]}'
)
CONTAINMENT_JSON = '{"claims": [{"text": "喜欢看分布式", "confidence": 0.5, "kind": "preference"}]}'
CONTAINMENT_LONG_JSON = (
    '{"claims": [{"text": "喜欢看分布式系统讲解", "confidence": 0.8, "kind": "preference"}]}'
)
NEW_CLAIM_JSON = '{"claims": [{"text": "关注数据库内核", "confidence": 0.5, "kind": "narrative"}]}'


class FakeLLM:
    """返回固定 claims JSON，记录 (system, user) 调用。"""

    def __init__(self, response: str = CLAIMS_JSON) -> None:
        self.response = response
        self.seen: tuple[str, str] | None = None

    async def chat(self, system: str, user: str) -> str:
        self.seen = (system, user)
        return "```json\n" + self.response + "\n```"


def _event(event_id: str, title: str = "分布式系统课程") -> dict:
    """构造事件 dict（与 api.events 契约一致）。"""
    return {
        "event_id": event_id,
        "type": "click",
        "url": "https://www.bilibili.com/video/BV1xx",
        "title": title,
        "source_platform": "bilibili",
        "context": {"pageType": "video", "scrollPosition": 120},
        "metadata": {},
    }


def _profile() -> Profile:
    return Profile(name="张三")


@pytest.mark.asyncio
async def test_ingest_events_creates_trial_claims_with_behavior_sources() -> None:
    llm = FakeLLM()
    pipeline = ProfileUpdatePipeline(llm=llm)
    original = _profile()
    updated = await pipeline.ingest_events(original, [_event("e-1")])

    assert len(updated.narrative_claims) == 2
    assert all(claim.state == "trial" for claim in updated.narrative_claims)
    assert all(claim.sources[0].kind == "behavior" for claim in updated.narrative_claims)
    assert updated.narrative_claims[0].text == "喜欢看分布式系统讲解"
    assert updated.narrative_claims[0].confidence == 0.8
    assert updated.narrative_claims[0].sources[0].ref == "e-1"
    assert original.narrative_claims == []  # 不修改传入对象
    assert llm.seen is not None
    assert llm.seen[0] == EVENT_TO_CLAIM_SYSTEM_PROMPT  # 静态 system 常量（prompt-cache 约定）
    assert "分布式系统课程" in llm.seen[1] and "bilibili" in llm.seen[1]


@pytest.mark.asyncio
async def test_ingest_events_repeated_text_accumulates_evidence() -> None:
    pipeline = ProfileUpdatePipeline(llm=FakeLLM())
    profile = _profile()
    profile = await pipeline.ingest_events(profile, [_event("e-1")])
    profile = await pipeline.ingest_events(profile, [_event("e-2")])
    profile = await pipeline.ingest_events(profile, [_event("e-3")])

    claim = next(c for c in profile.narrative_claims if c.text == "喜欢看分布式系统讲解")
    assert claim.evidence_count == 2
    assert [s.ref for s in claim.sources] == ["e-1", "e-2", "e-3"]


@pytest.mark.asyncio
async def test_ingest_events_containment_merges_into_existing() -> None:
    short = ProfileUpdatePipeline(llm=FakeLLM(response=CONTAINMENT_JSON))
    profile = await short.ingest_events(_profile(), [_event("e-1")])
    assert [c.text for c in profile.narrative_claims] == ["喜欢看分布式"]

    long = ProfileUpdatePipeline(llm=FakeLLM(response=CONTAINMENT_LONG_JSON))
    merged = await long.ingest_events(profile, [_event("e-2")])
    assert len(merged.narrative_claims) == 1
    assert merged.narrative_claims[0].text == "喜欢看分布式"
    assert merged.narrative_claims[0].evidence_count == 1


@pytest.mark.asyncio
async def test_ingest_events_different_text_adds_new_claim() -> None:
    first = ProfileUpdatePipeline(llm=FakeLLM())
    profile = await first.ingest_events(_profile(), [_event("e-1")])
    other = ProfileUpdatePipeline(llm=FakeLLM(response=NEW_CLAIM_JSON))
    updated = await other.ingest_events(profile, [_event("e-9")])

    assert [c.text for c in updated.narrative_claims] == [
        "喜欢看分布式系统讲解",
        "关注后端基础设施方向",
        "关注数据库内核",
    ]


def test_events_ingest_cli(tmp_path) -> None:
    jsonl = tmp_path / "events.jsonl"
    db = tmp_path / "talentforge.db"
    jsonl.write_text(
        "\n".join(
            [
                json.dumps(_event("e-1"), ensure_ascii=False),
                json.dumps(_event("e-2", title="知乎问答"), ensure_ascii=False),
                json.dumps(_event("e-1"), ensure_ascii=False),
                "not-json{{",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(main, ["events-ingest", str(jsonl), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"ingested": 2, "duplicates": 1, "invalid": 1}
    assert len(list_events(init_db(db))) == 2


def test_profile_update_cli(monkeypatch, tmp_path) -> None:
    db = tmp_path / "talentforge.db"
    conn = init_db(db)
    for i in range(3):
        insert_event(
            conn,
            event_id=f"u-{i}",
            event_type="click",
            url="https://www.bilibili.com/video/BV1xx",
            title="分布式系统",
            source_platform="bilibili",
            context_json=json.dumps({"pageType": "video"}),
            metadata_json="",
            received_at=f"2026-08-2{i}T12:00:00+00:00",
        )
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps({"name": "张三"}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(cli_module, "_build_llm", lambda: FakeLLM())
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["profile-update", "--profile", str(profile_file), "--limit", "3", "--db", str(db)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"added_claims": 2, "updated_claims": 0}

    saved = json.loads(profile_file.read_text(encoding="utf-8"))
    assert len(saved["narrative_claims"]) == 2
    assert all(claim["state"] == "trial" for claim in saved["narrative_claims"])
    assert saved["narrative_claims"][0]["sources"][0]["kind"] == "behavior"

    again = runner.invoke(
        main,
        ["profile-update", "--profile", str(profile_file), "--limit", "3", "--db", str(db)],
    )
    assert json.loads(again.output) == {"added_claims": 0, "updated_claims": 2}
