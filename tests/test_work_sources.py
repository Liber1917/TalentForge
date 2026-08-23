"""M5 Task 1 测试：作品分级规则表逐条（R1-R8 + CCF 查表 + 短路顺序）
+ 三源采集器（MockTransport 注入，不真联网）+ WorkStore 持久化。

规则表来源 docs/spec-m5-work-sources.md §2（D24 信号理论，全规则版无 LLM）；
Link header commits 计数（per_page=1 时 last 页码 = 总数，无 Link = 1）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from talentforge.domain.work import WorkArtifact
from talentforge.sources.work_grading import grade_paper, grade_repo, match_ccf_venue
from talentforge.sources.work_sources import (
    ArxivSource,
    GiteeSource,
    GitHubSource,
    WorkSourceError,
    parse_arxiv_feed,
)
from talentforge.work.store import WorkStore


def _repo_facts(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        stars=10,
        forks=2,
        is_fork=False,
        language="Python",
        languages={"Python": 800, "Shell": 200},  # 恰 80%，不触发 R8
        commits=50,
        span_days=30,
        pushed_at="2024-05-01T00:00:00Z",
    )
    defaults.update(overrides)
    return defaults


def _paper_facts(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        authors=["张三", "李四"],
        first_author="张三",
        year=2024,
        venue="NeurIPS",
        summary="摘要",
    )
    defaults.update(overrides)
    return defaults


def _artifact(aid: str = "github:alice/proj", **overrides: Any) -> WorkArtifact:
    defaults: dict[str, Any] = dict(
        artifact_id=aid,
        platform="github",
        kind="repo",
        title="proj",
        url="https://github.com/alice/proj",
        facts={"stars": 1},
    )
    defaults.update(overrides)
    return WorkArtifact(**defaults)  # type: ignore[arg-type]


# ---------- 分级规则表：grade_repo ----------


def test_r1_fork_short_circuits_to_weak_even_with_many_commits() -> None:
    grade, reasons = grade_repo(_repo_facts(is_fork=True, commits=500, span_days=400))
    assert grade == "weak"
    assert any(r.startswith("R1:") for r in reasons)


def test_r2_few_commits_is_weak() -> None:
    grade, reasons = grade_repo(_repo_facts(commits=5))
    assert grade == "weak"
    assert any(r.startswith("R2:") for r in reasons)


def test_r3_six_month_span_is_strong() -> None:
    grade, reasons = grade_repo(_repo_facts(commits=50, span_days=200))
    assert grade == "strong"
    assert any(r.startswith("R3:") for r in reasons)


def test_r3_span_derived_from_first_and_last_commit() -> None:
    facts = _repo_facts(
        span_days=None,  # 走 first/last_commit 推导路径
        first_commit="2023-01-01T00:00:00Z",
        last_commit="2023-12-01T00:00:00Z",
    )
    grade, reasons = grade_repo(facts)
    assert grade == "strong"  # 334 天 ≥ 180
    assert any(r.startswith("R3:") for r in reasons)


def test_r7_stars_only_record_reason_never_grade() -> None:
    # fork + 大 stars 仍 weak：stars 可刷，不抬 grade
    grade, reasons = grade_repo(_repo_facts(is_fork=True, stars=10000))
    assert grade == "weak"
    assert any(r.startswith("R7:") for r in reasons)
    # 无 fork：stars 不改变缺省 normal
    grade2, reasons2 = grade_repo(_repo_facts(stars=10000))
    assert grade2 == "normal"
    assert any(r.startswith("R7:") for r in reasons2)


def test_r8_dominant_language_appends_reason_without_grade() -> None:
    grade, reasons = grade_repo(_repo_facts(languages={"Python": 900, "Go": 100}))
    assert grade == "normal"  # R8 只附 reason 不判 grade
    assert any(r.startswith("R8:") for r in reasons)
    # 占比恰 80% 不触发（需 >80%）
    _, reasons80 = grade_repo(_repo_facts(languages={"Python": 80, "Go": 20}))
    assert not any(r.startswith("R8:") for r in reasons80)


def test_repo_default_converges_to_normal() -> None:
    grade, _ = grade_repo(_repo_facts())
    assert grade == "normal"


# ---------- 分级规则表：grade_paper ----------


def test_r4_first_author_with_ccf_venue_is_strong() -> None:
    grade, reasons = grade_paper(_paper_facts(venue="NeurIPS"))
    assert grade == "strong"
    assert any(r.startswith("R4:") for r in reasons)


def test_r5_first_author_non_top_venue_is_normal() -> None:
    grade, reasons = grade_paper(_paper_facts(venue="某大学学报"))
    assert grade == "normal"
    assert any(r.startswith("R5:") for r in reasons)


def test_r6_non_first_author_top_venue_is_normal() -> None:
    grade, reasons = grade_paper(_paper_facts(authors=["王五", "张三"], venue="CVPR"))
    assert grade == "normal"
    assert any(r.startswith("R6:") for r in reasons)


def test_preprint_without_venue_caps_at_normal() -> None:
    grade, reasons = grade_paper(_paper_facts(venue=""))
    assert grade == "normal"
    assert any(r.startswith("R5:") for r in reasons)


def test_ccf_table_matches_case_insensitive() -> None:
    assert match_ccf_venue("neurips") == "neurips"
    assert match_ccf_venue("Proceedings of ICML 2024") == "icml"
    assert match_ccf_venue("IEEE S&P 2025") == "s&p"
    assert match_ccf_venue("Journal of Ordinary Studies") == ""
    grade, _ = grade_paper(_paper_facts(venue="neurips"))  # 全小写也命中
    assert grade == "strong"


# ---------- GitHubSource ----------


def _gh_commit(sha: str, date: str) -> dict[str, Any]:
    return {"sha": sha, "commit": {"author": {"name": "alice", "date": date}}}


def _github_handler(seen: dict[str, Any]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        path = request.url.path
        page = request.url.params.get("page", "1")
        if path == "/users/alice/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "proj",
                        "full_name": "alice/proj",
                        "fork": False,
                        "stargazers_count": 42,
                        "forks_count": 3,
                        "language": "Python",
                        "pushed_at": "2024-06-01T00:00:00Z",
                        "html_url": "https://github.com/alice/proj",
                    },
                    {
                        "name": "forked",
                        "full_name": "alice/forked",
                        "fork": True,
                        "stargazers_count": 1,
                        "forks_count": 0,
                        "language": "C",
                        "pushed_at": "2024-06-01T00:00:00Z",
                        "html_url": "https://github.com/alice/forked",
                    },
                ],
            )
        if path == "/repos/alice/proj/languages":
            return httpx.Response(200, json={"Python": 900, "Shell": 100})
        if path == "/repos/alice/proj/commits":
            if page == "1":
                return httpx.Response(
                    200,
                    json=[_gh_commit("late", "2024-01-01T00:00:00Z")],
                    headers={
                        "link": (
                            '<https://api.github.com/repos/alice/proj/commits'
                            '?per_page=1&page=37>; rel="last", '
                            '<https://api.github.com/repos/alice/proj/commits'
                            '?per_page=1&page=2>; rel="next"'
                        )
                    },
                )
            return httpx.Response(200, json=[_gh_commit("early", "2023-01-01T00:00:00Z")])
        if path == "/repos/alice/forked/languages":
            return httpx.Response(200, json={"C": 100})
        if path == "/repos/alice/forked/commits":
            # 无 Link header → commits = 1
            return httpx.Response(200, json=[_gh_commit("only", "2024-05-01T00:00:00Z")])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_github_source_fetches_and_grades() -> None:
    seen: dict[str, Any] = {}
    source = GitHubSource(transport=_github_handler(seen))
    artifacts = await source.fetch_user_works("alice")
    assert seen["auth"] == ""  # 未配 token 无 Authorization
    assert [a.artifact_id for a in artifacts] == ["github:alice/proj", "github:alice/forked"]
    proj, forked = artifacts
    assert proj.platform == "github" and proj.kind == "repo"
    assert proj.facts["commits"] == 37  # Link last 页码
    assert proj.facts["span_days"] == 365
    assert proj.facts["stars"] == 42
    assert proj.facts["language"] == "Python"
    assert proj.facts["languages"] == {"Python": 900, "Shell": 100}
    assert proj.grade == "strong"
    assert any(r.startswith("R3:") for r in proj.grade_reasons)
    assert forked.grade == "weak"  # fork 不排除采集，只降 grade
    assert forked.facts["commits"] == 1  # 无 Link = 1
    assert any(r.startswith("R1:") for r in forked.grade_reasons)


async def test_github_token_env_sets_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTFORGE_GITHUB_TOKEN", "gh-token-1")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=[])

    source = GitHubSource(transport=httpx.MockTransport(handler))
    assert await source.fetch_user_works("alice") == []
    assert seen["auth"] == "Bearer gh-token-1"


async def test_github_rate_limit_raises_with_token_hint() -> None:
    source = GitHubSource(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(WorkSourceError, match="TALENTFORGE_GITHUB_TOKEN"):
        await source.fetch_user_works("alice")


# ---------- GiteeSource ----------


async def test_gitee_source_fetches_and_grades() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        page = request.url.params.get("page", "1")
        if path == "/api/v5/users/bob/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "tools",
                        "full_name": "bob/tools",
                        "fork": False,
                        "stargazers_count": 7,
                        "forks_count": 1,
                        "language": "Go",
                        "pushed_at": "2024-03-01T00:00:00+08:00",
                        "html_url": "https://gitee.com/bob/tools",
                    }
                ],
            )
        if path == "/api/v5/repos/bob/tools/languages":
            return httpx.Response(200, json={"Go": 500})
        if path == "/api/v5/repos/bob/tools/commits":
            if page == "1":
                return httpx.Response(
                    200,
                    json=[_gh_commit("late", "2024-01-01T00:00:00+08:00")],
                    headers={
                        "link": (
                            "<https://gitee.com/api/v5/repos/bob/tools/commits"
                            '?per_page=1&page=25>; rel="last"'
                        )
                    },
                )
            return httpx.Response(200, json=[_gh_commit("early", "2023-01-01T00:00:00+08:00")])
        return httpx.Response(404)

    source = GiteeSource(transport=httpx.MockTransport(handler))
    artifacts = await source.fetch_user_works("bob")
    assert len(artifacts) == 1
    a = artifacts[0]
    assert a.artifact_id == "gitee:bob/tools"
    assert a.platform == "gitee"
    assert a.facts["commits"] == 25
    assert a.facts["span_days"] == 365
    assert a.facts["language"] == "Go"
    assert a.grade == "strong"


# ---------- ArxivSource ----------

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv query</title>
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Paper One
       A Study</title>
    <summary> Long summary
      with newlines. </summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Li Si</name></author>
    <author><name>Zhang San</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v2</id>
    <title>Deep Something Accepted at NeurIPS 2023</title>
    <summary>Second summary.</summary>
    <published>2023-11-01T00:00:00Z</published>
    <author><name>Zhang San</name></author>
    <author><name>Wang Wu</name></author>
  </entry>
</feed>
"""


async def test_arxiv_source_parses_feed_and_grades() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/query"
        assert request.url.params.get("search_query") == 'au:"Zhang San"'
        assert request.url.params.get("max_results") == "50"
        return httpx.Response(
            200, text=ARXIV_XML, headers={"content-type": "application/atom+xml; charset=utf-8"}
        )

    source = ArxivSource(transport=httpx.MockTransport(handler))
    artifacts = await source.fetch_author_papers("Zhang San")
    assert [a.artifact_id for a in artifacts] == ["arxiv:2401.00001v1", "arxiv:2401.00002v2"]
    first, second = artifacts
    assert first.kind == "paper"
    assert first.title == "Paper One A Study"  # 空白折叠
    assert first.facts["authors"] == ["Li Si", "Zhang San"]  # 作者顺序保留
    assert first.facts["first_author"] == "Zhang San"
    assert first.facts["year"] == 2024
    assert first.facts["venue"] == ""  # preprint 无 venue
    assert first.grade == "normal"  # normal 封顶
    assert second.facts["venue"] == "neurips"  # 标题含会议名 → 查表命中
    assert second.grade == "strong"  # 一作 + CCF
    assert second.facts["summary"] == "Second summary."


async def test_arxiv_summary_truncated_to_300_chars() -> None:
    xml = ARXIV_XML.replace("Second summary.", "x" * 500)

    source = ArxivSource(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=xml)))
    artifacts = await source.fetch_author_papers("Zhang San")
    assert len(artifacts[1].facts["summary"]) == 300
    assert len(parse_arxiv_feed(xml)[1]["summary"]) == 500  # 解析层不截断


def test_parse_arxiv_feed_rejects_bad_xml() -> None:
    with pytest.raises(WorkSourceError):
        parse_arxiv_feed("not-xml<")


# ---------- WorkStore ----------


def test_store_upsert_merges_by_artifact_id(tmp_path: Path) -> None:
    store = WorkStore(tmp_path / "artifacts.json")
    assert store.upsert_all([_artifact("github:a"), _artifact("github:b")]) == 2
    assert store.upsert_all([_artifact("github:a", facts={"stars": 99})]) == 0  # 更新不新增
    by_id = {a.artifact_id: a for a in store.list_all()}
    assert set(by_id) == {"github:a", "github:b"}
    assert by_id["github:a"].facts["stars"] == 99


def test_store_dismiss_roundtrip_and_persistence(tmp_path: Path) -> None:
    path = tmp_path / "artifacts.json"
    store = WorkStore(path)
    store.upsert_all([_artifact("github:a")])
    assert not store.is_dismissed("github:a")
    store.dismiss("github:a")
    store.dismiss("github:a")  # 幂等
    assert store.is_dismissed("github:a")
    reloaded = WorkStore(path)
    assert reloaded.is_dismissed("github:a")  # 落盘
    assert [a.artifact_id for a in reloaded.list_all()] == ["github:a"]


def test_store_tolerates_missing_and_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "artifacts.json"
    store = WorkStore(path)
    assert store.list_all() == []  # 缺失 → 空库
    assert not store.is_dismissed("github:a")
    path.write_text("not-json{", encoding="utf-8")
    assert store.list_all() == []  # 损坏 → 告警按空库
    assert store.upsert_all([_artifact("github:a")]) == 1
    assert len(WorkStore(path).list_all()) == 1


def test_store_env_path_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / "env_artifacts.json"
    monkeypatch.setenv("TALENTFORGE_ARTIFACTS_PATH", str(env_path))
    WorkStore().upsert_all([_artifact("github:a")])
    assert env_path.exists()
