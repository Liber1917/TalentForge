"""FastAPI 应用测试：/api/health、/api/events 幂等契约、静态根占位、CORS。"""

from __future__ import annotations

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


def test_cors_headers_permissive() -> None:
    client = _client()
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "*"
