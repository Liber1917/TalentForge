"""M5 Task 4 简历产出页测试：GET /cv 聚合渲染（画像姓名/技能/作品 title）、
画像缺失占位提示、works 按 grade 排序（strong 在前）、active 主张渲染 / trial 不渲染。

注入方式（同 test_api_work._make_client）：
- TALENTFORGE_PROFILE_PATH → tmp profile.json（从 docs/demo 拷贝后追加 1 条 active 主张，
  demo 自带 6 条 trial claim，正好验证 trial 不上简历）
- work.store.ARTIFACTS_PATH → tmp artifacts.json（WorkStore.upsert_all 直接写库）
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.api.common import DEFAULT_PROFILE_PATH
from talentforge.domain.work import WorkArtifact
from talentforge.storage.db import init_db
from talentforge.work import store as work_store
from talentforge.work.store import WorkStore

ACTIVE_CLAIM = "有大规模分布式系统落地经验"
TRIAL_CLAIM = "用户对后端开发中的异步编程技术有深入学习的兴趣"  # demo 自带 trial 主张


def _repo(aid: str, title: str, grade: str, **overrides: Any) -> WorkArtifact:
    defaults: dict[str, Any] = dict(
        artifact_id=aid,
        platform="github",
        kind="repo",
        title=title,
        url=f"https://github.com/alice/{title}",
        facts={"language": "Python", "commits": 120, "stars": 12},
        grade=grade,
        grade_reasons=[],
    )
    defaults.update(overrides)
    return WorkArtifact(**defaults)  # type: ignore[arg-type]


def _make_client(
    monkeypatch: Any, tmp_path: Path, *, with_profile: bool = True
) -> TestClient:
    """tmp 画像 + tmp 作品库 + 内存库；with_profile=True 时从 demo 拷贝并追加 active 主张。"""
    profile_path = tmp_path / "profile.json"
    if with_profile:
        shutil.copy(DEFAULT_PROFILE_PATH, profile_path)
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        data["narrative_claims"].append(
            {
                "text": ACTIVE_CLAIM,
                "state": "active",
                "evidence_count": 2,
                "confidence": 0.8,
                "sources": [],
            }
        )
        profile_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(profile_path))
    monkeypatch.delenv("TALENTFORGE_ARTIFACTS_PATH", raising=False)
    monkeypatch.setattr(work_store, "ARTIFACTS_PATH", tmp_path / "artifacts.json")
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn))


def _write_works(tmp_path: Path, artifacts: list[WorkArtifact]) -> None:
    WorkStore(tmp_path / "artifacts.json").upsert_all(artifacts)


# ---------- GET /cv：聚合渲染 + /resume 旧路径跳转 ----------


def test_resume_renders_profile_skills_and_works(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    _write_works(
        tmp_path,
        [
            _repo("github:alice/web-crawler", "web-crawler", "strong"),
            _repo("github:alice/toy-cli", "toy-cli", "weak"),
        ],
    )

    response = client.get("/cv")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "示例候选人（Demo）" in html  # 画像姓名
    assert "深耕后端基础设施的工程师" in html  # narrative.identity
    assert "Python" in html  # 技能 pill
    assert "web-crawler" in html  # 作品 title
    assert "toy-cli" in html
    assert "120 commits" in html  # facts 摘要
    assert "window.print" in html  # 打印/导出 PDF 按钮在线


def test_resume_missing_profile_shows_placeholder(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path, with_profile=False)

    response = client.get("/cv")
    assert response.status_code == 200
    assert "上传" in response.text or "暂无" in response.text


# ---------- works 排序与过滤 ----------


def test_resume_sorts_works_strong_first(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    _write_works(
        tmp_path,
        [
            _repo("github:alice/toy-cli", "toy-cli", "weak"),
            _repo("github:alice/mid-lab", "mid-lab", "normal"),
            _repo("github:alice/web-crawler", "web-crawler", "strong"),
        ],
    )

    html = client.get("/cv").text
    assert html.index("web-crawler") < html.index("mid-lab") < html.index("toy-cli")


# ---------- claims 过滤：active 上简历、trial 不上 ----------


def test_resume_renders_active_claims_only(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)

    html = client.get("/cv").text
    assert ACTIVE_CLAIM in html
    assert TRIAL_CLAIM not in html


def test_resume_legacy_path_redirects_to_cv(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path, with_profile=False)
    resp = client.get("/resume", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/cv"
