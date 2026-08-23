"""M5 Task 2 作品路由测试：fetch 三源编排（单源降级）+ artifacts 列表 +
claims 写画像（grade→confidence / 去重 / 驳回排除）+ dismiss 幂等。

注入方式（参照 test_api_feedback._make_client）：
- TALENTFORGE_PROFILE_PATH → tmp profile.json（claims 用例从 docs/demo 拷贝，
  demo 自带 6 条 trial claim，便于验证追加不动旧主张）
- work.store.ARTIFACTS_PATH → tmp artifacts.json（路由经 work_store 模块引用）
- 三源不打真实网络：monkeypatch routes_work.GitHubSource/GiteeSource/ArxivSource
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from talentforge.api import routes_work
from talentforge.api.app import create_app
from talentforge.api.common import DEFAULT_PROFILE_PATH
from talentforge.domain.work import WorkArtifact
from talentforge.sources.work_sources import WorkSourceError
from talentforge.storage.db import init_db
from talentforge.work import store as work_store

REPO_ID = "github:alice/web-crawler"
PAPER_ID = "arxiv:2401.00001"


def _repo(
    aid: str = REPO_ID, grade: str = "strong", **overrides: Any
) -> WorkArtifact:
    defaults: dict[str, Any] = dict(
        artifact_id=aid,
        platform="github",
        kind="repo",
        title="web-crawler",
        url="https://github.com/alice/web-crawler",
        facts={"language": "Python", "commits": 120, "stars": 12, "span_days": 300},
        grade=grade,
        grade_reasons=["R3: 持续 commit ≥ 6 个月"],
    )
    defaults.update(overrides)
    return WorkArtifact(**defaults)  # type: ignore[arg-type]


def _paper(
    aid: str = PAPER_ID, grade: str = "normal", **overrides: Any
) -> WorkArtifact:
    defaults: dict[str, Any] = dict(
        artifact_id=aid,
        platform="arxiv",
        kind="paper",
        title="Raft Replication in Practice",
        url="https://arxiv.org/abs/2401.00001",
        facts={
            "authors": ["Alice Chen", "Bob Li"],
            "first_author": "Alice Chen",
            "year": 2024,
            "venue": "ICSE",
            "summary": "摘要",
        },
        grade=grade,
        grade_reasons=["R5: CCF-C 或非顶会一作"],
    )
    defaults.update(overrides)
    return WorkArtifact(**defaults)  # type: ignore[arg-type]


def _fake_source(artifacts: list[WorkArtifact] | None = None, error: Exception | None = None):
    """替身源类：github/gitee 走 fetch_user_works、arxiv 走 fetch_author_papers。"""

    class _FakeSource:
        async def fetch_user_works(self, username: str) -> list[WorkArtifact]:
            if error is not None:
                raise error
            return list(artifacts or [])

        async def fetch_author_papers(self, author: str) -> list[WorkArtifact]:
            if error is not None:
                raise error
            return list(artifacts or [])

    return _FakeSource


def _make_client(
    monkeypatch: Any, tmp_path: Path, *, with_demo_profile: bool = False
) -> TestClient:
    """tmp 画像 + tmp 作品库 + 内存库；with_demo_profile=True 时从 demo 拷贝画像。

    内容探针（D29）同样不打真实网络/LLM：默认以 noop 探针替代（恒 None 不
    降级，本文件只测编排；探针联动在 test_content_probe.py 覆盖）。
    """
    profile_path = tmp_path / "profile.json"
    if with_demo_profile:
        shutil.copy(DEFAULT_PROFILE_PATH, profile_path)
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(profile_path))
    monkeypatch.delenv("TALENTFORGE_ARTIFACTS_PATH", raising=False)
    monkeypatch.setattr(work_store, "ARTIFACTS_PATH", tmp_path / "artifacts.json")
    monkeypatch.setattr(routes_work, "probe_content", _noop_probe)
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn))


async def _noop_probe(
    full_name: str, llm: Any, transport: Any = None
) -> dict[str, Any] | None:
    """无操作探针：恒返回 None（不降级），保持老用例与探针解耦。"""
    return None


def _fetch(client: TestClient, body: dict) -> dict:
    response = client.post("/api/work/fetch", json=body)
    assert response.status_code == 200
    return response.json()


def _saved_claims(tmp_path: Path) -> list[dict]:
    data = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    return data["narrative_claims"]


# ---------- POST /api/work/fetch ----------


def test_fetch_merges_three_sources_with_partial_failure_warning(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        routes_work,
        "GitHubSource",
        _fake_source([_repo(), _repo(aid="github:alice/raft-lab", title="raft-lab")]),
    )
    monkeypatch.setattr(
        routes_work,
        "GiteeSource",
        _fake_source(error=WorkSourceError("Gitee 限流，请稍后重试")),
    )
    monkeypatch.setattr(routes_work, "ArxivSource", _fake_source([_paper()]))

    data = _fetch(
        client,
        {"github_user": "alice", "gitee_user": "alice", "arxiv_author": "Alice Chen"},
    )
    assert data["ok"] is True
    assert data["total_fetched"] == 3
    assert data["added"] == 3
    assert data["warnings"] == ["gitee: Gitee 限流，请稍后重试"]

    listing = client.get("/api/work/artifacts").json()
    assert len(listing["artifacts"]) == 3
    assert listing["dismissed"] == []


def test_fetch_without_sources_is_noop(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    data = _fetch(client, {})
    assert data == {"ok": True, "total_fetched": 0, "added": 0, "warnings": []}


def test_fetch_refetch_counts_added_only_for_new(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_work, "GitHubSource", _fake_source([_repo()]))

    assert _fetch(client, {"github_user": "alice"})["added"] == 1
    again = _fetch(client, {"github_user": "alice"})
    assert again["total_fetched"] == 1
    assert again["added"] == 0  # upsert merge：已存在按更新计
    assert len(client.get("/api/work/artifacts").json()["artifacts"]) == 1


# ---------- GET /api/work/artifacts + POST /api/work/dismiss ----------


def test_dismiss_marks_artifact_and_is_idempotent(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_work, "GitHubSource", _fake_source([_repo()]))
    _fetch(client, {"github_user": "alice"})

    first = client.post("/api/work/dismiss", json={"artifact_id": REPO_ID})
    assert first.status_code == 200
    assert first.json() == {"ok": True}

    listing = client.get("/api/work/artifacts").json()
    assert [a["artifact_id"] for a in listing["artifacts"]] == [REPO_ID]  # 仍在列表
    assert listing["dismissed"] == [REPO_ID]

    assert client.post("/api/work/dismiss", json={"artifact_id": REPO_ID}).json()["ok"] is True
    assert client.get("/api/work/artifacts").json()["dismissed"] == [REPO_ID]  # 幂等不重复


# ---------- POST /api/work/claims ----------


def test_claims_all_writes_active_claims_with_grade_confidence(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, with_demo_profile=True)
    monkeypatch.setattr(
        routes_work,
        "GitHubSource",
        _fake_source(
            [
                _repo(),  # strong → 0.9
                _repo(aid="github:alice/toy-cli", title="toy-cli", grade="weak"),  # weak → 0.5
            ]
        ),
    )
    monkeypatch.setattr(routes_work, "ArxivSource", _fake_source([_paper()]))  # normal → 0.7
    _fetch(client, {"github_user": "alice", "arxiv_author": "Alice Chen"})

    response = client.post("/api/work/claims", json={"all": True})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "written": 3, "skipped": 0}

    claims = _saved_claims(tmp_path)
    assert len(claims) == 6 + 3  # demo 6 条不动，追加 3 条
    by_text = {c["text"]: c for c in claims[-3:]}
    assert by_text["GitHub 项目 web-crawler（Python，120 commits，强信号）"] == {
        "text": "GitHub 项目 web-crawler（Python，120 commits，强信号）",
        "state": "active",
        "evidence_count": 1,
        "confidence": 0.9,
        "sources": [{"kind": "work", "ref": REPO_ID}],
    }
    assert by_text["GitHub 项目 toy-cli（Python，120 commits，弱信号）"]["confidence"] == 0.5
    assert (
        by_text["arXiv 论文《Raft Replication in Practice》（2024，一作，ICSE）"][
            "confidence"
        ]
        == 0.7
    )


def test_claims_same_text_second_write_is_skipped(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, with_demo_profile=True)
    monkeypatch.setattr(routes_work, "ArxivSource", _fake_source([_paper()]))
    _fetch(client, {"arxiv_author": "Alice Chen"})

    assert client.post("/api/work/claims", json={"all": True}).json()["written"] == 1
    second = client.post("/api/work/claims", json={"all": True}).json()
    assert second == {"ok": True, "written": 0, "skipped": 1}
    assert len(_saved_claims(tmp_path)) == 6 + 1  # 二写不重复


def test_claims_exclude_dismissed_and_honor_artifact_ids(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, with_demo_profile=True)
    monkeypatch.setattr(
        routes_work,
        "GitHubSource",
        _fake_source([_repo(), _repo(aid="github:alice/raft-lab", title="raft-lab")]),
    )
    _fetch(client, {"github_user": "alice"})
    client.post("/api/work/dismiss", json={"artifact_id": REPO_ID})

    by_ids = client.post(
        "/api/work/claims", json={"artifact_ids": [REPO_ID, "github:alice/raft-lab"]}
    ).json()
    assert by_ids == {"ok": True, "written": 1, "skipped": 0}  # 驳回的按 id 也不写
    texts = [c["text"] for c in _saved_claims(tmp_path)]
    assert "GitHub 项目 raft-lab（Python，120 commits，强信号）" in texts
    assert "GitHub 项目 web-crawler（Python，120 commits，强信号）" not in texts

    dismissed_all = client.post("/api/work/claims", json={"all": True}).json()
    assert dismissed_all == {"ok": True, "written": 0, "skipped": 1}  # 仅剩已写那条去重


def test_claims_missing_profile_starts_from_empty(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, with_demo_profile=False)
    monkeypatch.setattr(routes_work, "GitHubSource", _fake_source([_repo()]))
    _fetch(client, {"github_user": "alice"})

    response = client.post("/api/work/claims", json={"all": True})
    assert response.status_code == 200
    assert response.json()["written"] == 1
    claims = _saved_claims(tmp_path)  # 画像文件缺失时空画像兜底落盘
    assert len(claims) == 1
    assert claims[0]["state"] == "active"


# ---------- 主张模板：一作判定/venue 缺省（纯函数） ----------


def test_paper_claim_text_coauthor_without_venue() -> None:
    paper = _paper(facts={"authors": ["Bob Li", "Alice Chen"], "first_author": "Alice Chen", "year": 2023, "venue": ""})
    assert routes_work._claim_text(paper) == "arXiv 论文《Raft Replication in Practice》（2023，合作者）"
