"""M9 岗位胜任力建模测试：聚类复用、模型缓存、逐维对齐解析、决策联动。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from talentforge.domain.competency import CompetencyModel
from talentforge.domain.job import Job
from talentforge.domain.match import FitLevel, Match
from talentforge.domain.profile import Profile
from talentforge.matcher.coarse import _parse_competency
from talentforge.report.generate import generate_report
from talentforge.sources.job_competency import (
    CompetencyModelCache,
    RuleCompetencyClusterer,
    _skills_of,
    _title_key,
)


def _job(id: str, title: str, description: str = "", tags: list[str] | None = None) -> Job:
    return Job(
        id=id, source="boss", title=title, company="C", location="S",
        url=f"https://x/{id}", description=description, tags=tags or [],
    )


def _profile() -> Profile:
    return Profile(name="测试", skills=["python"], deal_breakers=[])


# ---------------- 聚类 ----------------


def test_title_key_normalizes_symbols_and_stopwords() -> None:
    assert _title_key("Python后端工程师") == "Python后端"
    assert _title_key("后端开发工程师") == "后端"
    assert _title_key("AI Infra 资深专家") == "AIInfra"


def test_cluster_groups_similar_jobs_and_separates_different() -> None:
    jobs = [
        _job("j1", "Python后端工程师", "Python Go Redis 高并发"),
        _job("j2", "后端开发工程师", "Go Python 分布式"),
        _job("j3", "前端工程师", "React Vue CSS"),
    ]
    clusterer = RuleCompetencyClusterer()
    clusters = clusterer.cluster(jobs)
    assert len(clusters) == 2
    backend = next(c for c in clusters if "j1" in c.member_job_ids)
    assert backend.member_job_ids == ["j1", "j2"]
    frontend = next(c for c in clusters if "j3" in c.member_job_ids)
    assert frontend.member_job_ids == ["j3"]


def test_find_cluster_returns_role_key_for_members() -> None:
    jobs = [_job("j1", "Python后端工程师", "Python Go"), _job("j2", "后端工程师", "Go Python")]
    clusterer = RuleCompetencyClusterer()
    clusterer.cluster(jobs)
    assert clusterer.find_cluster(jobs[0]) is not None
    assert clusterer.find_cluster(jobs[0]) == clusterer.find_cluster(jobs[1])


def test_skills_of_ignores_english_boilerplate() -> None:
    job = _job(
        "j1",
        "海外增长运营",
        "We are looking for a passionate engineer. You will join our team "
        "and build amazing products with the company. 3.5年经验，16薪。",
    )
    assert _skills_of(job) == set()


def test_skills_of_matches_real_tech_tokens() -> None:
    job = _job(
        "j1",
        "后端工程师",
        "熟悉 JavaScript、gRPC、C++、Node.js、Vue3、K8s、PostgreSQL、Redis、Docker 与 mysql",
    )
    assert {
        "javascript", "grpc", "c++", "node.js", "vue3",
        "k8s", "postgresql", "redis", "docker", "mysql",
    } <= _skills_of(job)


def test_english_boilerplate_does_not_merge_unrelated_jobs() -> None:
    jobs = [
        _job(
            "j1", "海外增长运营",
            "We are looking for a passionate engineer to join our team "
            "and build amazing products with the company.",
        ),
        _job(
            "j2", "本地生活BD",
            "We are looking for a passionate marketer to join our team "
            "and build amazing products with the company.",
        ),
    ]
    clusters = RuleCompetencyClusterer().cluster(jobs)
    assert len(clusters) == 2


# ---------------- 模型缓存 ----------------


def test_cache_roundtrip_and_corrupt_tolerance(tmp_path: Path) -> None:
    cache = CompetencyModelCache(tmp_path / "cm.json")
    assert cache.load() == {}
    model = CompetencyModel(role="后端", role_key="backend", dimensions=[{"name": "认知复杂度"}])
    cache.put(model)
    loaded = CompetencyModelCache(tmp_path / "cm.json").load()
    assert loaded["backend"].dimensions[0].name == "认知复杂度"

    (tmp_path / "cm.json").write_text("{not-json", encoding="utf-8")
    assert CompetencyModelCache(tmp_path / "cm.json").load() == {}


def test_cache_invalidates_on_clusterer_version_mismatch(tmp_path: Path) -> None:
    legacy = CompetencyModel(role="后端", role_key="backend", dimensions=[{"name": "认知复杂度"}])
    p = tmp_path / "cm.json"

    # rule-v1 时代写的缓存 → 当前 rule-v2 聚类语义下整体作废
    p.write_text(
        json.dumps({"_version": "rule-v1", "backend": legacy.model_dump()}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert CompetencyModelCache(p, version="rule-v2").load() == {}

    # 更旧的扁平格式（无 _version 字段）→ 同样作废
    p.write_text(
        json.dumps({"backend": legacy.model_dump()}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert CompetencyModelCache(p).load() == {}


def test_cache_persists_version_header(tmp_path: Path) -> None:
    cache = CompetencyModelCache(tmp_path / "cm.json", version="rule-v2")
    cache.put(CompetencyModel(role="后端", role_key="backend", dimensions=[{"name": "韧性"}]))
    data = json.loads((tmp_path / "cm.json").read_text(encoding="utf-8"))
    assert data["_version"] == "rule-v2"


# ---------------- 逐维对齐解析 ----------------


def test_parse_competency_tolerant_and_truncates() -> None:
    items = _parse_competency(
        [
            {"dimension": "认知复杂度", "candidate_level": "strong", "evidence_refs": ["e1"]},
            {"dimension": "Python能力", "candidate_level": "invalid"},  # 非法 level → missing
            {"dimension": "", "candidate_level": "strong"},  # 空维度 → 跳过
            "not-a-dict",
        ]
    )
    assert [a.dimension for a in items] == ["认知复杂度", "Python能力"]
    assert items[0].candidate_level == "strong"
    assert items[1].candidate_level == "missing"


def test_parse_competency_empty_for_missing_field() -> None:
    assert _parse_competency(None) == []
    assert _parse_competency({"not": "a list"}) == []


# ---------------- 决策联动（generate_report 集成） ----------------


class FakeLlmCompetency:
    """FakeLLM：返回含 competency 的匹配 JSON。"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def chat(self, system: str, user: str) -> str:
        return json.dumps(self._payload, ensure_ascii=False)


async def _run_report(monkeypatch: Any, tmp_path: Path, competency: list[dict]) -> dict:
    from talentforge.storage.db import init_db

    monkeypatch.setenv("TALENTFORGE_COMPETENCY_CACHE", str(tmp_path / "cm.json"))
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials", lambda: ("", "", "")
    )
    llm = FakeLlmCompetency(
        {
            "market_fit": "high",
            "growth_fit": "high",
            "reasoning": ["ok"],
            "matched": ["a"],
            "missing": [],
            "gaps": [],
            "competency": competency,
        }
    )
    from talentforge.matcher.coarse import CoarseMatcher

    jobs = [
        _job("j1", "Python后端工程师", "Python Go 高并发"),
        _job("j2", "后端工程师", "Go Python 分布式"),
    ]
    return await generate_report(
        _profile(), "后端", "上海", limit=2, jobs=jobs,
        matcher=CoarseMatcher(llm), conn=init_db(":memory:"),
    )


@pytest.mark.asyncio
async def test_competency_carried_into_report_items(monkeypatch: Any, tmp_path: Path) -> None:
    report = await _run_report(
        monkeypatch, tmp_path,
        [{"dimension": "认知复杂度", "candidate_level": "strong", "evidence_refs": ["e1"]}],
    )
    item = report["items"][0]
    assert item["competency"][0]["dimension"] == "认知复杂度"
    assert item["competency"][0]["candidate_level"] == "strong"


@pytest.mark.asyncio
async def test_apply_downgraded_to_hold_when_two_dimensions_missing(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # market/growth 双 high → 本来 apply；但 2 维 missing → 降级 hold
    report = await _run_report(
        monkeypatch, tmp_path,
        [
            {"dimension": "认知复杂度", "candidate_level": "missing"},
            {"dimension": "韧性", "candidate_level": "missing"},
        ],
    )
    assert report["items"][0]["verdict"] == "hold"
    assert report["summary"]["n_apply"] == 0
    assert report["summary"]["n_hold"] == 2


@pytest.mark.asyncio
async def test_competency_model_cached_and_reused(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # 首轮建模型 → 缓存文件存在且含 role_key
    await _run_report(
        monkeypatch, tmp_path,
        [{"dimension": "认知复杂度", "candidate_level": "strong"}],
    )
    cache_path = tmp_path / "cm.json"
    assert cache_path.exists()
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert any("Python" in k or "后端" in k for k in data)
