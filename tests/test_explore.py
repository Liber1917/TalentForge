"""M7 方向探索器测试：build_asset_brief（纯数据）/ build_market_stats（词频）/
_parse_card（形状校验+截断+clamp）/ generate_snapshot（FakeLLM 容错）/
DirectionStore（快照替换保修正卡 + upsert）/ API 三端点（FakeLLM + tmp 路径
monkeypatch + 内存库，同 test_content_probe 注入方式，不打真实 API）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.domain.direction import DirectionCard
from talentforge.domain.job import Job
from talentforge.domain.profile import (
    ExploitationRedline,
    NarrativeClaim,
    Profile,
    StructuralPosition,
)
from talentforge.domain.work import WorkArtifact
from talentforge.explore import store as explore_store
from talentforge.explore.engine import (
    EXPLORE_SNAPSHOT_SYSTEM_PROMPT,
    _parse_card,
    build_asset_brief,
    build_market_stats,
    card_id_for,
    generate_snapshot,
)
from talentforge.explore.store import DirectionStore
from talentforge.storage.db import init_db
from talentforge.work import store as work_store

# ---------- 造数 ----------


def _profile() -> Profile:
    return Profile(
        name="alice",
        years_experience=3.0,
        skills=["C", "Python"],
        desired_roles=["嵌入式软件工程师"],
        deal_breakers=["996"],
        structural_position=StructuralPosition(
            cash_buffer="约6个月",
            stage="探索期",
            city_constraints=["上海"],
            exploitation_redlines=[ExploitationRedline(kind="996", stance="never")],
        ),
        narrative_claims=[
            NarrativeClaim(text="对边缘部署有持续兴趣", state="trial"),
            NarrativeClaim(text="长期维护嵌入式开源项目", state="active"),
        ],
    )


def _artifact(
    title: str = "edge-ai-hub",
    grade: str = "strong",
    language: str = "C",
    commits: int = 35,
) -> WorkArtifact:
    return WorkArtifact(
        artifact_id=f"github:alice/{title}",
        platform="github",
        kind="repo",
        title=title,
        url=f"https://github.com/alice/{title}",
        facts={"language": language, "commits": commits},
        grade=grade,  # type: ignore[arg-type]
    )


def _job(title: str) -> Job:
    return Job(
        source="boss",
        title=title,
        company="某公司",
        location="上海",
        url=f"https://example.com/{title}",
    )


def _card_json(scope: str = "track", title: str = "边缘 AI 部署", **overrides: Any) -> dict:
    data: dict[str, Any] = {
        "scope": scope,
        "title": title,
        "why_you": [
            {
                "kind": "work",
                "ref": "github:alice/edge-ai-hub",
                "text": "edge-ai-hub（C，35 commits）",
            }
        ],
        "market_evidence": "岗位统计中边缘类关键词密集",
        "data_backed": True,
        "distance": "差一个可展示的部署案例",
        "first_step": "把 demo 部署到开发板",
        "constraint_check": ["现金缓冲约6个月，允许一次试错"],
        "confidence": 0.7,
    }
    data.update(overrides)
    return data


def _card(
    scope: str = "track", title: str = "边缘 AI 部署", created_from: str = ""
) -> DirectionCard:
    return DirectionCard(
        card_id=card_id_for(title),
        scope=scope,  # type: ignore[arg-type]
        title=title,
        created_from=created_from,
    )


class _FakeLLM:
    """替身 LLM：记录 (system, user)，可回放固定输出或抛错（同 test_content_probe）。"""

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.seen: tuple[str, str] | None = None

    async def chat(self, system: str, user: str) -> str:
        self.seen = (system, user)
        if self.error is not None:
            raise self.error
        return self.reply


# ---------- build_asset_brief（纯数据） ----------


def test_brief_strong_works_and_claims_routed_correctly() -> None:
    brief = build_asset_brief(
        _profile(),
        [
            _artifact(),
            _artifact(title="notes", grade="weak", language="Python", commits=2),
        ],
    )
    assert {"language": "C", "repos": 1} in brief["skill_clusters"]
    assert {"language": "Python", "repos": 1} in brief["skill_clusters"]
    joined = " ".join(brief["strong_signals"])
    assert "edge-ai-hub" in joined and "35 commits" in joined  # strong 作品进清单
    assert "长期维护嵌入式开源项目" in joined  # active 主张进清单
    assert "notes" not in joined  # weak 作品不进强信号
    assert brief["behavior_interests"] == ["对边缘部署有持续兴趣"]  # trial 主张进兴趣


def test_brief_structural_summary_and_hard_boundaries_complete() -> None:
    brief = build_asset_brief(_profile(), [])
    summary = brief["structural_summary"]
    assert summary["cash_buffer"] == "约6个月"
    assert summary["stage"] == "探索期"
    assert summary["city_constraints"] == ["上海"]
    assert summary["family_payback"] == "否"
    hard = brief["hard_boundaries"]
    assert hard["deal_breakers"] == ["996"]
    assert hard["exploitation_redlines"] == ["996（绝不）"]
    assert brief["basics"] == {
        "years_experience": 3.0,
        "skills": ["C", "Python"],
        "desired_roles": ["嵌入式软件工程师"],
    }


def test_brief_empty_inputs_do_not_crash() -> None:
    brief = build_asset_brief(Profile(name=""), [])
    assert brief["skill_clusters"] == []
    assert brief["strong_signals"] == []
    assert brief["behavior_interests"] == []
    assert brief["hard_boundaries"] == {"deal_breakers": [], "exploitation_redlines": []}
    assert brief["structural_summary"]["cash_buffer"] == ""


# ---------- build_market_stats（词频粗统计） ----------


def test_market_stats_counts_keyword_frequency() -> None:
    stats = build_market_stats(
        [
            _job("AI 算法工程师"),
            _job("AI infra 工程师"),
            _job("嵌入式软件工程师"),
        ]
    )
    assert stats["total_jobs"] == 3
    assert stats["title_keywords"][0] == {"keyword": "AI", "count": 2}  # 唯一高频词
    counts = {e["keyword"]: e["count"] for e in stats["title_keywords"]}
    assert counts["infra"] == 1
    assert counts["嵌入式软件工程师"] == 1


def test_market_stats_splits_on_slash_and_drops_single_char() -> None:
    stats = build_market_stats([_job("高级AI工程师/AI应用 C 端")])
    keywords = [e["keyword"] for e in stats["title_keywords"]]
    assert "高级AI工程师" in keywords  # 斜杠拆分
    assert "AI应用" in keywords
    assert "C" not in keywords  # 1 字词丢弃
    assert "端" not in keywords


def test_market_stats_empty_jobs() -> None:
    assert build_market_stats([]) == {"total_jobs": 0, "title_keywords": []}


# ---------- _parse_card（形状校验 + 截断 + clamp） ----------


def test_parse_card_valid_passthrough_with_stable_id() -> None:
    card = _parse_card(_card_json())
    assert card is not None
    assert card.card_id == card_id_for("边缘 AI 部署")
    assert card.card_id.startswith("dir-") and len(card.card_id) == 16
    assert card.scope == "track"
    assert card.why_you[0].kind == "work"
    assert card.data_backed is True
    assert card.confidence == 0.7
    assert card.created_from == ""


def test_parse_card_rejects_bad_scope_or_missing_title() -> None:
    assert _parse_card(_card_json(scope="galaxy")) is None
    assert _parse_card("not-a-dict") is None
    assert _parse_card({"scope": "track"}) is None  # 无标题
    assert _parse_card({"scope": "track", "title": ""}) is None


def test_parse_card_truncates_long_fields() -> None:
    card = _parse_card(
        _card_json(
            title="方" * 100,
            market_evidence="市" * 500,
            distance="差" * 300,
            first_step="步" * 300,
            constraint_check=["约" * 200],
        )
    )
    assert card is not None
    assert len(card.title) == 60
    assert len(card.market_evidence) == 300
    assert len(card.distance) == 200
    assert len(card.first_step) == 200
    assert len(card.constraint_check[0]) == 120
    assert card.card_id == card_id_for("方" * 60)  # 截断后标题再哈希


def test_parse_card_clamps_confidence_and_tolerates_bad_values() -> None:
    high = _parse_card(_card_json(confidence=1.7))
    low = _parse_card(_card_json(confidence=-0.5))
    bad = _parse_card(_card_json(confidence="高"))
    assert high is not None and high.confidence == 1.0
    assert low is not None and low.confidence == 0.0
    assert bad is not None and bad.confidence == 0.5


def test_parse_card_skips_bad_evidence_entries_not_whole_card() -> None:
    card = _parse_card(
        _card_json(why_you=["not-a-dict", {"kind": "work", "ref": "r", "text": "ok"}, {"ref": "x"}])
    )
    assert card is not None
    assert len(card.why_you) == 1
    assert card.why_you[0].text == "ok"


def test_parse_card_coerces_data_backed_strictly() -> None:
    assert _parse_card(_card_json(data_backed=False)).data_backed is False
    assert _parse_card(_card_json(data_backed="true")).data_backed is True
    assert _parse_card(_card_json(data_backed="有数据")).data_backed is False


# ---------- generate_snapshot（FakeLLM 容错） ----------


def _snapshot_reply(directions: list[Any]) -> str:
    return json.dumps({"directions": directions}, ensure_ascii=False)


async def test_snapshot_valid_output_returns_cards_with_stable_ids() -> None:
    llm = _FakeLLM(
        reply=_snapshot_reply(
            [
                _card_json(),
                _card_json(scope="lifestyle", title="初创核心工程师"),
                _card_json(scope="field", title="沪上边缘圈"),
            ]
        )
    )
    cards, error = await generate_snapshot(_profile(), [_artifact()], [_job("AI 工程师")], llm)
    assert error == ""
    assert [c.title for c in cards] == ["边缘 AI 部署", "初创核心工程师", "沪上边缘圈"]
    assert cards[0].card_id == card_id_for("边缘 AI 部署")
    system, user = llm.seen or ("", "")
    assert system == EXPLORE_SNAPSHOT_SYSTEM_PROMPT  # prompt-cache：system 零变量
    assert "资产盘点" in user and "岗位市场统计" in user
    assert "edge-ai-hub" in user and "total_jobs" in user  # 盘点+统计都在 user 侧


async def test_snapshot_garbage_output_returns_empty_with_error() -> None:
    llm = _FakeLLM(reply="抱歉，我无法输出 JSON。")
    cards, error = await generate_snapshot(_profile(), [], [], llm)
    assert cards == []
    assert error


async def test_snapshot_llm_exception_returns_empty_with_error() -> None:
    llm = _FakeLLM(error=RuntimeError("LLM 未配置"))
    cards, error = await generate_snapshot(_profile(), [], [], llm)
    assert cards == []
    assert error


async def test_snapshot_directions_not_list_returns_parse_error() -> None:
    llm = _FakeLLM(reply='{"directions": "nope"}')
    cards, error = await generate_snapshot(_profile(), [], [], llm)
    assert cards == []
    assert "解析失败" in error


async def test_snapshot_mixed_cards_skips_bad_keeps_good() -> None:
    llm = _FakeLLM(
        reply=_snapshot_reply(
            [
                {"scope": "galaxy", "title": "坏口径"},
                _card_json(),
                "not-a-dict",
                {"scope": "track"},  # 无标题
            ]
        )
    )
    cards, error = await generate_snapshot(_profile(), [], [], llm)
    assert error == ""
    assert len(cards) == 1 and cards[0].title == "边缘 AI 部署"


async def test_snapshot_all_cards_invalid_returns_parse_error() -> None:
    llm = _FakeLLM(reply=_snapshot_reply([{"scope": "galaxy", "title": "坏"}, {"scope": "x"}]))
    cards, error = await generate_snapshot(_profile(), [], [], llm)
    assert cards == []
    assert "解析失败" in error


# ---------- DirectionStore ----------


def test_store_replace_all_preserves_revised_cards(tmp_path: Path) -> None:
    store = DirectionStore(tmp_path / "directions.json")
    store.replace_all([_card(), _card(scope="lifestyle", title="大厂部门")])

    revised = _card(created_from="snap-1")  # 深谈修正卡（同 id 整条更新）
    revised.market_evidence = "深谈修正：聚焦边缘部署"
    store.upsert_card(revised)

    store.replace_all([_card(scope="field", title="沪上边缘圈")])  # 新快照替换
    cards = store.list_all()
    assert [c.title for c in cards] == ["沪上边缘圈", "边缘 AI 部署"]  # 旧快照卡被清、修正卡保留
    kept = cards[1]
    assert kept.created_from == "snap-1"
    assert kept.market_evidence == "深谈修正：聚焦边缘部署"


def test_store_replace_all_revised_overrides_same_id_snapshot(tmp_path: Path) -> None:
    store = DirectionStore(tmp_path / "directions.json")
    store.upsert_card(_card(created_from="snap-1"))
    store.replace_all([_card()])  # 同标题同 card_id 的新快照卡
    cards = store.list_all()
    assert len(cards) == 1
    assert cards[0].created_from == "snap-1"  # 修正卡优先，不被冲掉


def test_store_upsert_replaces_by_id_or_appends(tmp_path: Path) -> None:
    store = DirectionStore(tmp_path / "directions.json")
    store.upsert_card(_card())
    updated = _card()
    updated.distance = "差一个部署案例"
    store.upsert_card(updated)
    cards = store.list_all()
    assert len(cards) == 1 and cards[0].distance == "差一个部署案例"  # 按 id 替换
    store.upsert_card(_card(scope="field", title="新日远程"))
    assert len(store.list_all()) == 2  # 无同 id 追加


def test_store_tolerates_missing_and_corrupt_file(tmp_path: Path) -> None:
    store = DirectionStore(tmp_path / "directions.json")
    assert store.list_all() == []  # 缺失静默空

    path = tmp_path / "directions.json"
    path.write_text("not-json", encoding="utf-8")
    assert DirectionStore(path).list_all() == []  # 损坏按空处理
    store = DirectionStore(path)
    store.upsert_card(_card())  # 损坏后仍可写回
    assert len(store.list_all()) == 1


# ---------- API 三端点 ----------


def _make_client(monkeypatch: Any, tmp_path: Path, llm: Any) -> TestClient:
    """tmp 画像 + tmp 作品库 + tmp 方向库 + 内存库（同 test_content_probe._make_client）。"""
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.delenv("TALENTFORGE_ARTIFACTS_PATH", raising=False)
    monkeypatch.delenv("TALENTFORGE_DIRECTIONS_PATH", raising=False)
    monkeypatch.setattr(work_store, "ARTIFACTS_PATH", tmp_path / "artifacts.json")
    monkeypatch.setattr(explore_store, "DIRECTIONS_PATH", tmp_path / "directions.json")
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn, llm=llm))


def _write_profile(tmp_path: Path) -> None:
    (tmp_path / "profile.json").write_text(_profile().model_dump_json(), encoding="utf-8")


def test_api_snapshot_contract(monkeypatch: Any, tmp_path: Path) -> None:
    llm = _FakeLLM(
        reply=_snapshot_reply(
            [
                _card_json(),
                _card_json(scope="lifestyle", title="初创核心"),
                _card_json(scope="field", title="沪上边缘圈"),
            ]
        )
    )
    client = _make_client(monkeypatch, tmp_path, llm)
    _write_profile(tmp_path)

    data = client.post("/api/explore/snapshot").json()
    assert data["ok"] is True and data["generated"] == 3 and data["error"] == ""
    titles = [d["title"] for d in data["directions"]]
    assert titles == ["边缘 AI 部署", "初创核心", "沪上边缘圈"]
    first = data["directions"][0]
    assert first["card_id"] == card_id_for("边缘 AI 部署")
    assert first["scope"] == "track"
    assert first["why_you"][0]["kind"] == "work"
    assert first["confidence"] == 0.7

    listed = client.get("/api/explore/directions").json()  # 落库后可读回
    assert [d["title"] for d in listed["directions"]] == titles


def test_api_snapshot_failure_returns_contract_not_500(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, _FakeLLM(error=RuntimeError("LLM 未配置")))
    _write_profile(tmp_path)
    data = client.post("/api/explore/snapshot").json()
    assert data["ok"] is False and data["generated"] == 0 and data["error"]
    assert client.get("/api/explore/directions").json()["directions"] == []


def test_api_snapshot_without_profile_falls_back_to_empty(
    monkeypatch: Any, tmp_path: Path
) -> None:
    llm = _FakeLLM(reply=_snapshot_reply([_card_json()]))
    client = _make_client(monkeypatch, tmp_path, llm)  # 画像文件不写
    data = client.post("/api/explore/snapshot").json()
    assert data["ok"] is True and data["generated"] == 1  # 空画像兜底不 404


def test_api_asset_brief_returns_brief(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path, _FakeLLM())
    _write_profile(tmp_path)
    brief = client.get("/api/explore/asset-brief").json()["brief"]
    assert brief is not None
    assert brief["hard_boundaries"]["deal_breakers"] == ["996"]
    assert brief["structural_summary"]["cash_buffer"] == "约6个月"
    assert brief["behavior_interests"] == ["对边缘部署有持续兴趣"]


def test_api_asset_brief_degrades_without_profile(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, _FakeLLM())
    resp = client.get("/api/explore/asset-brief").json()
    assert resp == {"brief": None, "reason": "暂无画像"}
