"""D29 内容探针测试：apply_probe_to_artifact 规则映射（纯函数）/
fetch_repo_evidence 三端点软降级（httpx.MockTransport）/ probe_content
LLM 输出形状校验（FakeLLM）/ fetch 端点集成（monkeypatch routes_work.probe_content
联动降级；探针不可用不降级不报错）。

注入方式同 test_api_work：tmp 画像 + tmp 作品库 + 内存库 + 替身源；
探针网络层一律 MockTransport、LLM 层一律 FakeLLM，不打真实 API。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from talentforge.api import routes_work
from talentforge.api.app import create_app
from talentforge.domain.work import WorkArtifact
from talentforge.sources.content_probe import (
    CONTENT_PROBE_SYSTEM_PROMPT,
    apply_probe_to_artifact,
    fetch_repo_evidence,
    probe_content,
)
from talentforge.sources.work_sources import UA
from talentforge.storage.db import init_db
from talentforge.work import store as work_store

REPO_ID = "github:alice/embedded-training"


# ---------- 造数 ----------


def _artifact(
    grade: str = "strong", platform: str = "github", repo: str = "embedded-training"
) -> WorkArtifact:
    aid = f"{platform}:alice/{repo}"
    return WorkArtifact(
        artifact_id=aid,
        platform=platform,  # type: ignore[arg-type]
        kind="repo",
        title=repo,
        url=f"https://{platform}.com/alice/{repo}",
        facts={"language": "C", "commits": 35, "span_days": 717},
        grade=grade,  # type: ignore[arg-type]
        grade_reasons=["R3: 持续 commit ≥6 个月（span 717 天），长期投入难伪造"],
    )


def _probe(content_type: str, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "content_type": content_type,
        "confidence": 0.85,
        "summary": "培训资料与学习路线收集",
        "evidence": ["顶层目录 learning-resources/ 为资料整理", "README: 嵌入式学习路线图"],
    }
    data.update(overrides)
    return data


class _FakeLLM:
    """替身 LLM：记录 (system, user)，可回放固定输出或抛错。"""

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.seen: tuple[str, str] | None = None

    async def chat(self, system: str, user: str) -> str:
        self.seen = (system, user)
        if self.error is not None:
            raise self.error
        return self.reply


def _ok_transport(handler: Any = None) -> httpx.MockTransport:
    """三端点全 200 的探针网络替身（handler 缺省给最小合法响应）。"""

    def default(request: httpx.Request) -> httpx.Response:
        del request
        readme = base64.b64encode("# 项目\n自研实现".encode()).decode("ascii")
        return httpx.Response(
            200,
            json={
                "content": readme,
                "entries_hint": None,
                "commits_hint": None,
            },
        )

    return httpx.MockTransport(handler or default)


# ---------- apply_probe_to_artifact（纯函数） ----------


def test_apply_documentation_strong_downgrades_to_normal_with_r9_evidence() -> None:
    result = apply_probe_to_artifact(_artifact(), _probe("documentation"))
    assert result.grade == "normal"
    reason = result.grade_reasons[-1]
    assert reason.startswith("R9: 内容探针判定资料收集型（证据：")
    assert "learning-resources/" in reason
    assert result.facts["content_probe"]["content_type"] == "documentation"
    # 保留原 R3 reason（可解释链完整）
    assert result.grade_reasons[0].startswith("R3:")


def test_apply_engineering_strong_keeps_grade_with_r9_note() -> None:
    result = apply_probe_to_artifact(_artifact(), _probe("engineering"))
    assert result.grade == "strong"
    assert result.grade_reasons[-1] == "R9: 内容探针：engineering（培训资料与学习路线收集）"


def test_apply_coursework_strong_keeps_grade() -> None:
    result = apply_probe_to_artifact(_artifact(), _probe("coursework"))
    assert result.grade == "strong"  # 只有 documentation 触发降级
    assert result.grade_reasons[-1].startswith("R9: 内容探针：coursework（")


def test_apply_documentation_normal_keeps_grade_noted() -> None:
    result = apply_probe_to_artifact(_artifact(grade="normal"), _probe("documentation"))
    assert result.grade == "normal"  # 本就 normal，无降级可做，仅附注
    assert result.grade_reasons[-1].startswith("R9: 内容探针：documentation（")


def test_apply_none_probe_returns_artifact_as_is() -> None:
    artifact = _artifact()
    result = apply_probe_to_artifact(artifact, None)
    assert result is artifact


def test_apply_is_pure_function_does_not_mutate_input() -> None:
    artifact = _artifact()
    apply_probe_to_artifact(artifact, _probe("documentation"))
    assert artifact.grade == "strong"
    assert "content_probe" not in artifact.facts
    assert len(artifact.grade_reasons) == 1


def test_apply_truncates_evidence_and_summary() -> None:
    long_evidence = "证" * 100
    long_summary = "查" * 100
    downgraded = apply_probe_to_artifact(
        _artifact(), _probe("documentation", evidence=[long_evidence], summary=long_summary)
    )
    assert "证据：" + "证" * 60 in downgraded.grade_reasons[-1]
    assert "证" * 61 not in downgraded.grade_reasons[-1]
    noted = apply_probe_to_artifact(
        _artifact(), _probe("mixed", evidence=[long_evidence], summary=long_summary)
    )
    assert "（" + "查" * 40 in noted.grade_reasons[-1]
    assert "查" * 41 not in noted.grade_reasons[-1]


def test_apply_empty_evidence_falls_back_to_summary_in_downgrade_reason() -> None:
    result = apply_probe_to_artifact(
        _artifact(), _probe("documentation", evidence=[], summary="路线图资料仓库")
    )
    assert result.grade == "normal"
    assert "R9: 内容探针判定资料收集型（证据：路线图资料仓库）" == result.grade_reasons[-1]


# ---------- fetch_repo_evidence（MockTransport 三端点） ----------


def _training_handler(request: httpx.Request) -> httpx.Response:
    readme = base64.b64encode(
        "# 嵌入式学习路线\n本仓库收集培训资料、路线图与课程模板。".encode()
    ).decode("ascii")
    path = request.url.path
    if path.endswith("/readme"):
        return httpx.Response(200, json={"content": readme})
    if path.endswith("/contents/"):
        return httpx.Response(
            200,
            json=[
                {"name": "src", "type": "dir"},
                {"name": "README.md", "type": "file"},
                {"name": "roadmaps", "type": "dir"},
            ],
        )
    if path.endswith("/commits"):
        assert request.url.params["per_page"] == "5"
        return httpx.Response(
            200,
            json=[
                {"commit": {"message": "add roadmap svg\n\n更新路线图素材"}},
                {"commit": {"message": "update resources"}},
            ],
        )
    return httpx.Response(404)


async def test_fetch_repo_evidence_collects_three_evidence_kinds() -> None:
    evidence = await fetch_repo_evidence(
        "alice/training", transport=httpx.MockTransport(_training_handler)
    )
    assert evidence["readme_head"].startswith("# 嵌入式学习路线")
    assert evidence["top_entries"] == ["src(dir)", "README.md(file)", "roadmaps(dir)"]
    assert evidence["recent_commits"] == ["add roadmap svg", "update resources"]


async def test_fetch_repo_evidence_truncates_readme_head() -> None:
    readme = base64.b64encode(("字" * 3000).encode("utf-8")).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(200, json={"content": readme})
        return httpx.Response(404)

    evidence = await fetch_repo_evidence("alice/repo", transport=httpx.MockTransport(handler))
    assert len(evidence["readme_head"]) == 2000


async def test_fetch_repo_evidence_readme_404_keeps_other_evidence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(404, json={"message": "Not Found"})
        return _training_handler(request)

    evidence = await fetch_repo_evidence("alice/repo", transport=httpx.MockTransport(handler))
    assert evidence["readme_head"] == ""
    assert evidence["top_entries"] != []
    assert evidence["recent_commits"] != []


async def test_fetch_repo_evidence_all_404_returns_empty_without_raising() -> None:
    evidence = await fetch_repo_evidence(
        "alice/repo", transport=httpx.MockTransport(lambda request: httpx.Response(404))
    )
    assert evidence == {"readme_head": "", "top_entries": [], "recent_commits": []}


async def test_fetch_repo_evidence_sends_token_and_ua_headers(monkeypatch: Any) -> None:
    monkeypatch.setenv("TALENTFORGE_GITHUB_TOKEN", "gh-probe-token")
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization", "")
        seen["ua"] = request.headers.get("User-Agent", "")
        return httpx.Response(404)

    await fetch_repo_evidence("alice/repo", transport=httpx.MockTransport(handler))
    assert seen["authorization"] == "Bearer gh-probe-token"
    assert seen["ua"] == UA


# ---------- probe_content（FakeLLM 形状校验） ----------


def _llm_reply() -> str:
    return (
        '{"content_type": "documentation", "confidence": 0.85, '
        '"evidence": ["README: 学习路线图", "目录 roadmaps/", "目录 docs/", "多余证据"], '
        '"summary": "资料收集型仓库"}'
    )


async def test_probe_content_valid_json_passes_shape_check() -> None:
    llm = _FakeLLM(reply=_llm_reply())
    result = await probe_content("alice/training", llm, transport=_ok_transport())
    assert result == {
        "content_type": "documentation",
        "confidence": 0.85,
        "summary": "资料收集型仓库",
        "evidence": ["README: 学习路线图", "目录 roadmaps/", "目录 docs/"],  # 最多 3 条
    }


async def test_probe_content_pins_static_system_and_full_name_in_user() -> None:
    llm = _FakeLLM(reply=_llm_reply())
    result = await probe_content("alice/training", llm, transport=_ok_transport())
    assert result is not None
    system, user = llm.seen or ("", "")
    assert system == CONTENT_PROBE_SYSTEM_PROMPT  # prompt-cache：system 零变量
    assert "alice/training" in user
    assert "README 开头" in user and "顶层目录/文件" in user and "最近提交信息" in user


async def test_probe_content_garbage_text_returns_none() -> None:
    llm = _FakeLLM(reply="抱歉，我无法输出 JSON。")
    assert await probe_content("alice/repo", llm, transport=_ok_transport()) is None


async def test_probe_content_llm_exception_returns_none() -> None:
    llm = _FakeLLM(error=RuntimeError("LLM 未配置"))
    assert await probe_content("alice/repo", llm, transport=_ok_transport()) is None


async def test_probe_content_bad_enum_or_evidence_shape_returns_none() -> None:
    bad_enum = _FakeLLM(
        reply='{"content_type": "vlog", "confidence": 0.9, "evidence": ["x"], "summary": "s"}'
    )
    assert await probe_content("alice/repo", bad_enum, transport=_ok_transport()) is None
    bad_evidence = _FakeLLM(
        reply='{"content_type": "engineering", "confidence": 0.9, '
        '"evidence": "not-a-list", "summary": "s"}'
    )
    assert await probe_content("alice/repo", bad_evidence, transport=_ok_transport()) is None


async def test_probe_content_clamps_confidence() -> None:
    llm = _FakeLLM(
        reply='{"content_type": "mixed", "confidence": 1.7, "evidence": ["x"], "summary": "s"}'
    )
    result = await probe_content("alice/repo", llm, transport=_ok_transport())
    assert result is not None and result["confidence"] == 1.0


async def test_probe_content_empty_evidence_bundle_returns_none() -> None:
    llm = _FakeLLM(reply=_llm_reply())
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    assert await probe_content("alice/repo", llm, transport=transport) is None
    assert llm.seen is None  # 证据全空时不再消耗 LLM 调用


# ---------- fetch 端点集成（monkeypatch routes_work.probe_content） ----------


def _make_client(monkeypatch: Any, tmp_path: Path) -> TestClient:
    """tmp 画像 + tmp 作品库 + 内存库（同 test_api_work._make_client）。"""
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.delenv("TALENTFORGE_ARTIFACTS_PATH", raising=False)
    monkeypatch.setattr(work_store, "ARTIFACTS_PATH", tmp_path / "artifacts.json")
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn))


def _fake_source(artifacts: list[WorkArtifact]):
    class _Src:
        async def fetch_user_works(self, username: str) -> list[WorkArtifact]:
            return list(artifacts)

    return _Src


def _stored(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/api/work/artifacts").json()["artifacts"]


def test_fetch_downgrades_strong_github_when_probe_says_documentation(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_work, "GitHubSource", _fake_source([_artifact()]))
    calls: list[str] = []

    async def fake_probe(
        full_name: str, llm: Any, transport: Any = None
    ) -> dict[str, Any] | None:
        calls.append(full_name)
        return _probe("documentation")

    monkeypatch.setattr(routes_work, "probe_content", fake_probe)

    data = client.post("/api/work/fetch", json={"github_user": "alice"}).json()
    assert data == {"ok": True, "total_fetched": 1, "added": 1, "warnings": []}
    assert calls == ["alice/embedded-training"]  # artifact_id 去前缀得 full_name

    stored = _stored(client)
    assert stored[0]["grade"] == "normal"
    assert stored[0]["facts"]["content_probe"]["content_type"] == "documentation"
    assert stored[0]["grade_reasons"][-1].startswith("R9: 内容探针判定资料收集型（证据：")


def test_fetch_keeps_strong_when_probe_unavailable(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_work, "GitHubSource", _fake_source([_artifact()]))

    async def none_probe(
        full_name: str, llm: Any, transport: Any = None
    ) -> dict[str, Any] | None:
        return None  # LLM 未配置/探针失败的软降级路径

    monkeypatch.setattr(routes_work, "probe_content", none_probe)

    data = client.post("/api/work/fetch", json={"github_user": "alice"}).json()
    assert data["ok"] is True and data["total_fetched"] == 1
    stored = _stored(client)
    assert stored[0]["grade"] == "strong"  # 不降级
    assert "content_probe" not in stored[0]["facts"]  # 不写入探针事实
    assert not any("R9" in r for r in stored[0]["grade_reasons"])


def test_fetch_probe_exception_skips_single_item_without_breaking(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_work, "GitHubSource", _fake_source([_artifact()]))

    async def boom(full_name: str, llm: Any, transport: Any = None) -> dict[str, Any] | None:
        raise RuntimeError("探针炸了")

    monkeypatch.setattr(routes_work, "probe_content", boom)

    data = client.post("/api/work/fetch", json={"github_user": "alice"}).json()
    assert data["ok"] is True
    assert _stored(client)[0]["grade"] == "strong"


def test_fetch_probes_only_github_strong_candidates(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        routes_work,
        "GitHubSource",
        _fake_source(
            [
                _artifact(grade="normal", repo="notes"),
                _artifact(),  # github strong → 探针目标
                _artifact(grade="weak", repo="tiny"),
            ]
        ),
    )
    monkeypatch.setattr(
        routes_work,
        "GiteeSource",
        _fake_source(
            [_artifact(grade="strong", platform="gitee", repo="training")]
        ),  # 非 github 不探
    )
    calls: list[str] = []

    async def fake_probe(
        full_name: str, llm: Any, transport: Any = None
    ) -> dict[str, Any] | None:
        calls.append(full_name)
        return _probe("engineering")

    monkeypatch.setattr(routes_work, "probe_content", fake_probe)

    data = client.post(
        "/api/work/fetch", json={"github_user": "alice", "gitee_user": "alice"}
    ).json()
    assert data["total_fetched"] == 4
    assert calls == ["alice/embedded-training"]  # 仅 github strong 一条被探

    by_id = {a["artifact_id"]: a for a in _stored(client)}
    assert by_id["gitee:alice/training"]["grade"] == "strong"  # gitee 不联动
    assert by_id["github:alice/embedded-training"]["grade"] == "strong"  # engineering 保持
    assert by_id["github:alice/embedded-training"]["grade_reasons"][-1].startswith(
        "R9: 内容探针：engineering（"
    )
    assert not any("R9" in r for r in by_id["gitee:alice/training"]["grade_reasons"])
