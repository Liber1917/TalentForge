"""M6 项目推荐器测试：filter_apt_projects 规则筛逐条（R-s1~R-s5 纯函数）/
search_repos（httpx.MockTransport，q/UA/token 断言 + 403 限流）/ suggest_projects
缓存（命中不调网络、TTL 过期重搜、文件容错）/ API 契约（monkeypatch
suggest_projects；for-job 读 decisions 内存缓存，无缓存 → 空）。

注入方式同 test_content_probe：MockTransport 网络、tmp 缓存文件
（monkeypatch project_suggest.SUGGESTIONS_PATH）、内存库 + TestClient。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from talentforge.api import routes_suggest
from talentforge.api.app import create_app
from talentforge.sources import project_suggest
from talentforge.sources.project_suggest import (
    filter_apt_projects,
    search_repos,
    suggest_projects,
)
from talentforge.sources.work_sources import UA, WorkSourceError
from talentforge.storage.db import init_db

GAP = "Kubernetes"
NOW = datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo(
    full_name: str = "alice/k8s-tool",
    stars: int = 500,
    days_ago: int = 5,
    issues: int = 50,
    description: str | None = "Kubernetes operator toolkit",
    language: str = "Go",
    fork: bool = False,
) -> dict[str, Any]:
    return {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "stargazers_count": stars,
        "open_issues_count": issues,
        "description": description,
        "language": language,
        "pushed_at": _iso(NOW - timedelta(days=days_ago)),
        "fork": fork,
    }


def _names(items: list[dict[str, Any]]) -> list[str]:
    return [item["full_name"] for item in items]


# ---------- filter_apt_projects（R-s1~R-s5 纯函数逐条） ----------


def test_filter_keeps_apt_repo_with_full_fields() -> None:
    items = filter_apt_projects([_repo()], GAP)
    assert len(items) == 1
    item = items[0]
    assert item == {
        "full_name": "alice/k8s-tool",
        "url": "https://github.com/alice/k8s-tool",
        "stars": 500,
        "description": "Kubernetes operator toolkit",
        "language": "Go",
        "pushed_at": _repo()["pushed_at"],
        "why": "规模适中·活跃·与 Kubernetes 相关",
    }


def test_filter_removes_low_stars() -> None:
    assert filter_apt_projects([_repo(stars=99)], GAP) == []


def test_filter_marks_huge_project_as_reference_only() -> None:
    items = filter_apt_projects([_repo(stars=50001)], GAP)
    assert len(items) == 1
    assert items[0]["why"] == "超大项目，参考为主·活跃·与 Kubernetes 相关"


def test_filter_removes_inactive_repo() -> None:
    assert filter_apt_projects([_repo(days_ago=31)], GAP) == []
    # 边界：恰好 30 天内（含当天推送）视为活跃
    assert filter_apt_projects([_repo(days_ago=29)], GAP) != []
    # pushed_at 缺失/无法解析按不活跃剔除
    assert filter_apt_projects([_repo() | {"pushed_at": ""}], GAP) == []
    assert filter_apt_projects([_repo() | {"pushed_at": "not-a-date"}], GAP) == []


def test_filter_removes_repo_with_too_many_open_issues() -> None:
    assert filter_apt_projects([_repo(issues=500)], GAP) == []
    assert filter_apt_projects([_repo(issues=499)], GAP) != []


def test_filter_removes_empty_or_unrelated_description_then_relaxes() -> None:
    # 严格 R-s4（有命中时）：不含 gap 关键词的描述被剔除，description 为空恒剔除
    repos = [
        _repo(full_name="a/miss", description="a web framework"),
        _repo(full_name="a/empty", description=""),
        _repo(full_name="a/hit", description=f"{GAP} operator toolkit"),
    ]
    assert _names(filter_apt_projects(repos, GAP)) == ["a/hit"]
    # 放宽回退：全被关键词剔光但描述非空 → 保留（why 不再声称与 gap 相关）
    items = filter_apt_projects([_repo(description="a web framework")], GAP)
    assert _names(items) == ["alice/k8s-tool"]
    assert items[0]["why"] == "规模适中·活跃·描述完整"
    # 关键词大小写不敏感
    assert filter_apt_projects([_repo(description="kubernetes K8S guide")], GAP) != []


def test_filter_relaxation_still_applies_hard_rules() -> None:
    # 放宽只豁免关键词命中：低星/不活跃/issues 超限/fork 依旧剔除
    repos = [
        _repo(full_name="a/low", stars=50, description="unrelated"),
        _repo(full_name="a/stale", days_ago=90, description="unrelated"),
        _repo(full_name="a/issues", issues=900, description="unrelated"),
        _repo(full_name="a/fork", fork=True, description="unrelated"),
        _repo(full_name="a/ok", description="unrelated but real project"),
    ]
    assert _names(filter_apt_projects(repos, GAP)) == ["a/ok"]


def test_filter_removes_fork() -> None:
    assert filter_apt_projects([_repo(fork=True)], GAP) == []


def test_filter_sorts_by_stars_desc_and_truncates_to_five() -> None:
    repos = [
        _repo(full_name=f"r/{i}", stars=200 + i, description=f"{GAP} helper {i}")
        for i in range(7)
    ]
    items = filter_apt_projects(repos, GAP)
    assert len(items) == 5
    assert [item["stars"] for item in items] == sorted(
        (item["stars"] for item in items), reverse=True
    )
    # 前五 = 星数最高的 r/6..r/2
    assert _names(items) == [f"r/{i}" for i in range(6, 1, -1)]


def test_filter_tolerates_garbage_shapes() -> None:
    repos: list[dict[str, Any]] = [
        "not-a-dict",  # type: ignore[list-item]
        {},
        _repo(full_name="a/ok"),
    ]
    assert _names(filter_apt_projects(repos, GAP)) == ["a/ok"]


# ---------- search_repos（MockTransport） ----------


def _search_transport(
    seen: dict[str, Any], response: httpx.Response | None = None
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["q"] = request.url.params.get("q", "")
        seen["sort"] = request.url.params.get("sort", "")
        seen["order"] = request.url.params.get("order", "")
        seen["per_page"] = request.url.params.get("per_page", "")
        seen["path"] = request.url.path
        seen["ua"] = request.headers.get("User-Agent", "")
        seen["authorization"] = request.headers.get("Authorization", "")
        if response is not None:
            return response
        return httpx.Response(200, json={"total_count": 1, "items": [_repo()]})

    return httpx.MockTransport(handler)


async def test_search_repos_builds_query_and_returns_items() -> None:
    seen: dict[str, Any] = {}
    repos = await search_repos(GAP, language="Go", transport=_search_transport(seen))
    assert seen["path"] == "/search/repositories"
    assert seen["q"] == "Kubernetes+language:Go"
    assert (seen["sort"], seen["order"], seen["per_page"]) == ("stars", "desc", "15")
    assert seen["ua"] == UA
    assert seen["authorization"] == ""
    assert repos == [_repo()]


async def test_search_repos_without_language_omits_filter() -> None:
    seen: dict[str, Any] = {}
    await search_repos(GAP, transport=_search_transport(seen))
    assert seen["q"] == "Kubernetes"


async def test_search_repos_sends_token_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTFORGE_GITHUB_TOKEN", "gh-suggest-token")
    seen: dict[str, Any] = {}
    await search_repos(GAP, transport=_search_transport(seen))
    assert seen["authorization"] == "Bearer gh-suggest-token"


async def test_search_repos_rate_limit_raises() -> None:
    for status in (403, 429):
        seen: dict[str, Any] = {}
        with pytest.raises(WorkSourceError, match="GitHub 搜索限流"):
            await search_repos(
                GAP, transport=_search_transport(seen, httpx.Response(status))
            )


async def test_search_repos_other_4xx_raises() -> None:
    seen: dict[str, Any] = {}
    with pytest.raises(WorkSourceError, match="HTTP 422"):
        await search_repos(
            GAP, transport=_search_transport(seen, httpx.Response(422))
        )


async def test_search_repos_network_error_raises() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(WorkSourceError, match="GitHub 搜索网络请求失败"):
        await search_repos(GAP, transport=httpx.MockTransport(boom))


async def test_search_repos_tolerates_bad_shape() -> None:
    seen: dict[str, Any] = {}
    # items 混入非 dict → 滤掉；整体非 dict → 空列表
    repos = await search_repos(
        GAP,
        transport=_search_transport(
            seen, httpx.Response(200, json={"items": [_repo(), "junk"]})
        ),
    )
    assert repos == [_repo()]
    repos = await search_repos(
        GAP, transport=_search_transport(seen, httpx.Response(200, json=[1, 2]))
    )
    assert repos == []


# ---------- suggest_projects（缓存：命中/TTL/容错） ----------


def _use_cache_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "suggestions.json"
    monkeypatch.setattr(project_suggest, "SUGGESTIONS_PATH", path)
    monkeypatch.delenv("TALENTFORGE_SUGGESTIONS_PATH", raising=False)
    return path


def _cached(items: list[dict[str, Any]], hours_ago: float = 1.0) -> dict[str, Any]:
    return {
        "items": items,
        "cached_at": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
    }


_CACHED_ITEM = {
    "full_name": "cached/repo",
    "url": "https://github.com/cached/repo",
    "stars": 300,
    "description": "cached hit",
    "language": "Go",
    "pushed_at": "",
    "why": "规模适中·活跃·描述完整",
}


async def test_suggest_cache_hit_skips_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _use_cache_file(monkeypatch, tmp_path)
    path.write_text(
        json.dumps({GAP: _cached([_CACHED_ITEM])}), encoding="utf-8"
    )
    # transport=None：若未命中会试图真实联网（测试环境即失败），命中则不炸
    assert await suggest_projects(GAP, transport=None) == [_CACHED_ITEM]


async def test_suggest_cache_miss_searches_filters_and_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _use_cache_file(monkeypatch, tmp_path)
    seen: dict[str, Any] = {}
    items = await suggest_projects(GAP, transport=_search_transport(seen))
    assert seen["q"] == GAP
    assert _names(items) == ["alice/k8s-tool"]
    cache = json.loads(path.read_text(encoding="utf-8"))
    assert cache[GAP]["items"] == items
    assert datetime.fromisoformat(cache[GAP]["cached_at"])


async def test_suggest_cache_expired_researches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _use_cache_file(monkeypatch, tmp_path)
    path.write_text(
        json.dumps({GAP: _cached([_CACHED_ITEM], hours_ago=25)}), encoding="utf-8"
    )
    items = await suggest_projects(GAP, transport=_search_transport({}))
    assert _names(items) == ["alice/k8s-tool"]  # 过期 → 重搜覆盖缓存条目
    cache = json.loads(path.read_text(encoding="utf-8"))
    assert _names(cache[GAP]["items"]) == ["alice/k8s-tool"]


async def test_suggest_corrupt_cache_file_treated_as_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _use_cache_file(monkeypatch, tmp_path)
    path.write_text("{not json", encoding="utf-8")
    items = await suggest_projects(GAP, transport=_search_transport({}))
    assert _names(items) == ["alice/k8s-tool"]
    assert json.loads(path.read_text(encoding="utf-8"))[GAP]["items"] == items


async def test_suggest_cache_entry_bad_timestamp_treated_as_expired(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _use_cache_file(monkeypatch, tmp_path)
    path.write_text(
        json.dumps({GAP: {"items": [_CACHED_ITEM], "cached_at": "junk"}}),
        encoding="utf-8",
    )
    items = await suggest_projects(GAP, transport=_search_transport({}))
    assert _names(items) == ["alice/k8s-tool"]


# ---------- API 契约（TestClient + monkeypatch suggest_projects） ----------


def _make_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """tmp 缓存 + 内存库（同 test_content_probe._make_client 风格）。"""
    _use_cache_file(monkeypatch, tmp_path)
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn))


def _stub_suggest(
    monkeypatch: pytest.MonkeyPatch, results: dict[str, list[dict[str, Any]]]
) -> list[str]:
    calls: list[str] = []

    async def fake(gap_skill: str, language: str = "", transport: Any = None):
        calls.append(f"{gap_skill}|{language}")
        if gap_skill in results:
            return results[gap_skill]
        raise WorkSourceError("GitHub 搜索限流，请配置 TALENTFORGE_GITHUB_TOKEN")

    monkeypatch.setattr(routes_suggest, "suggest_projects", fake)
    return calls


def test_suggest_endpoint_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    calls = _stub_suggest(monkeypatch, {GAP: [_CACHED_ITEM]})
    data = client.post("/api/suggest", json={"gap_skill": GAP}).json()
    assert data == {"ok": True, "gap_skill": GAP, "suggestions": [_CACHED_ITEM]}
    assert calls == [f"{GAP}|"]  # 未传 language → 空串


def test_suggest_endpoint_passes_language(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    calls = _stub_suggest(monkeypatch, {GAP: []})
    data = client.post(
        "/api/suggest", json={"gap_skill": GAP, "language": "Rust"}
    ).json()
    assert data["ok"] is True and data["suggestions"] == []
    assert calls == [f"{GAP}|Rust"]


def test_for_job_without_decision_cache_returns_empty_gaps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    calls = _stub_suggest(monkeypatch, {})
    data = client.post("/api/suggest/for-job", json={"job_url": "https://j/1"}).json()
    assert data == {"ok": True, "gaps": []}
    assert calls == []


def test_for_job_without_gaps_returns_empty_gaps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    _stub_suggest(monkeypatch, {})
    client.app.state.decisions["https://j/1"] = {"verdict": "apply", "gaps": []}
    data = client.post("/api/suggest/for-job", json={"job_url": "https://j/1"}).json()
    assert data == {"ok": True, "gaps": []}


def test_for_job_suggests_per_gap_and_passes_profile_language(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    profile_path = tmp_path / "profile.json"
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(profile_path))
    profile_path.write_text(
        json.dumps({"name": "alice", "skills": ["Go", "Python"]}), encoding="utf-8"
    )
    calls = _stub_suggest(monkeypatch, {"Kubernetes": [_CACHED_ITEM], "Rust": []})
    client.app.state.decisions["https://j/1"] = {
        "verdict": "hold",
        "gaps": [
            {"skill": "Kubernetes", "severity": "major", "evidence": "JD 要求"},
            {"skill": "Rust", "severity": "minor", "evidence": "画像无记录"},
        ],
    }
    data = client.post("/api/suggest/for-job", json={"job_url": "https://j/1"}).json()
    assert data == {
        "ok": True,
        "results": [
            {"skill": "Kubernetes", "severity": "major", "suggestions": [_CACHED_ITEM]},
            {"skill": "Rust", "severity": "minor", "suggestions": []},
        ],
    }
    # language 取画像主语言 skills[0]
    assert calls == ["Kubernetes|Go", "Rust|Go"]


def test_for_job_missing_profile_uses_empty_language(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(tmp_path / "nope.json"))
    calls = _stub_suggest(monkeypatch, {"Kubernetes": []})
    client.app.state.decisions["https://j/1"] = {
        "verdict": "hold",
        "gaps": [{"skill": "Kubernetes", "severity": "major"}],
    }
    data = client.post("/api/suggest/for-job", json={"job_url": "https://j/1"}).json()
    assert data["ok"] is True and len(data["results"]) == 1
    assert calls == ["Kubernetes|"]


def test_for_job_single_gap_failure_records_warning_not_breaking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    _stub_suggest(monkeypatch, {"Rust": []})  # Kubernetes → WorkSourceError
    client.app.state.decisions["https://j/1"] = {
        "verdict": "hold",
        "gaps": [
            {"skill": "Kubernetes", "severity": "major"},
            {"skill": "Rust", "severity": "minor"},
        ],
    }
    data = client.post("/api/suggest/for-job", json={"job_url": "https://j/1"}).json()
    assert data["ok"] is True
    k8s, rust = data["results"]
    assert k8s["suggestions"] == []
    assert "GitHub 搜索限流" in k8s["warning"]
    assert "warning" not in rust
    assert rust["suggestions"] == []


def test_for_job_skips_malformed_gap_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(tmp_path / "nope.json"))
    calls = _stub_suggest(monkeypatch, {"Kubernetes": []})
    client.app.state.decisions["https://j/1"] = {
        "gaps": ["junk-entry", {"severity": "major"}, {"skill": "Kubernetes"}],
    }
    data = client.post("/api/suggest/for-job", json={"job_url": "https://j/1"}).json()
    assert data == {
        "ok": True,
        "results": [{"skill": "Kubernetes", "severity": "", "suggestions": []}],
    }
    assert calls == ["Kubernetes|"]
