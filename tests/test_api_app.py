"""FastAPI 应用测试：/api/health、/api/events 幂等契约、静态根占位、CORS。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.storage.db import init_db


def _event(event_id: str, **overrides: object) -> dict:
    data: dict[str, object] = {
        "event_id": event_id,
        "type": "click",
        "url": "https://www.bilibili.com/video/BV1xx",
        "title": "Python 教程",
        "source_platform": "bilibili",
        "context": {"pageType": "video", "scrollPosition": 120},
        "metadata": {},
        "timestamp": "2026-08-21T12:00:00+00:00",
    }
    data.update(overrides)
    return data


def _client(web_dir: str | Path | None = None) -> TestClient:
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn, web_dir=web_dir))


def test_health_ok() -> None:
    client = _client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_events_valid_then_duplicate() -> None:
    client = _client()
    payload = {"events": [_event("api-1")]}

    first = client.post("/api/events", json=payload)
    assert first.status_code == 200
    assert first.json() == {"ok": True, "accepted": 1, "duplicates": 0, "rejected": []}

    second = client.post("/api/events", json=payload)
    assert second.status_code == 200
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1


def test_events_missing_event_id_rejected_400() -> None:
    client = _client()
    payload = {"events": [{"type": "click", "url": "https://x.com/a", "source_platform": "zhihu"}]}
    response = client.post("/api/events", json=payload)
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["rejected"] != []
    assert response.json()["accepted"] == 0


def test_root_404_when_web_dir_has_no_index_html(tmp_path: Path) -> None:
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "DESIGN.md").write_text("# design", encoding="utf-8")
    client = _client(web_dir=web_dir)
    assert client.get("/").status_code == 404


def test_root_serves_index_html_when_present(tmp_path: Path) -> None:
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<html>placeholder</html>", encoding="utf-8")
    client = _client(web_dir=web_dir)
    response = client.get("/")
    assert response.status_code == 200
    assert "placeholder" in response.text


def test_origin_guard_replaces_permissive_cors() -> None:
    """M10 安全批次：宽松 CORS（access-control-allow-origin: *）已移除。

    本地服务改为 Origin 守卫——本机 Origin 放行但不再回 CORS 通配头；
    跨站 Origin（如恶意网页）直接 403。
    """
    client = _client()
    # 本机 Origin 放行，但不再有通配 CORS 头
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    # 跨站 Origin 拒绝
    evil = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert evil.status_code == 403


def test_dns_rebinding_foreign_host_rejected() -> None:
    """DNS rebinding：攻击页把域名重绑到 127.0.0.1 后，浏览器视为同源 fetch——
    请求不带 Origin 头，仅查 Origin 的守卫会放行。Host 必须限本机。
    """
    client = _client()
    assert client.get("/api/health", headers={"Host": "127.0.0.1:8420"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "localhost:8420"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "[::1]:8420"}).status_code == 200
    evil = client.get("/api/health", headers={"Host": "evil.example.com:8420"})
    assert evil.status_code == 403


def test_profile_snapshot_loaded_when_file_present(tmp_path: Path, monkeypatch) -> None:
    """画像文件存在时 create_app 必须加载快照。

    曾因 load_profile 未导入，NameError 被 except Exception 静默吞掉——
    快照恒为 None，M10 回测地基从未工作过。
    """
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"name": "张三", "skills": ["python"]}), encoding="utf-8")
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(profile))
    conn = init_db(":memory:", check_same_thread=False)
    app = create_app(conn=conn)
    assert app.state.profile_snapshot is not None
    assert app.state.profile_snapshot["name"] == "张三"


def test_profile_snapshot_none_when_file_missing(tmp_path: Path, monkeypatch) -> None:
    """画像缺失不阻断启动：快照为 None，服务照常可用（except 路径不得炸）。"""
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(tmp_path / "absent.json"))
    conn = init_db(":memory:", check_same_thread=False)
    app = create_app(conn=conn)
    assert app.state.profile_snapshot is None
    client = TestClient(app)
    assert client.get("/api/health").json() == {"ok": True}
