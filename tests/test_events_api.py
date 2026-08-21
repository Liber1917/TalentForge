"""最小事件接收 API 测试：handle_events 校验/幂等 + events_server 实测 HTTP 端点。"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time

from talentforge.api.events import events_server, handle_events
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


def test_handle_events_idempotent_same_event_id() -> None:
    conn = init_db(":memory:")
    payload = {"events": [_event("e-1"), _event("e-1")]}
    result = handle_events(payload, conn)
    assert result == {"ok": True, "accepted": 1, "duplicates": 1, "rejected": []}
    again = handle_events({"events": [_event("e-1")]}, conn)
    assert again == {"ok": True, "accepted": 0, "duplicates": 1, "rejected": []}


def test_handle_events_missing_event_id_rejected() -> None:
    conn = init_db(":memory:")
    payload = {"events": [{"type": "click", "url": "https://x.com/a", "source_platform": "zhihu"}]}
    result = handle_events(payload, conn)
    assert result["ok"] is False
    assert result["rejected"] != []
    assert result["accepted"] == 0


def test_handle_events_three_valid_accepted() -> None:
    conn = init_db(":memory:")
    payload = {"events": [_event(f"e-{i}") for i in range(3)]}
    result = handle_events(payload, conn)
    assert result["ok"] is True
    assert result["accepted"] == 3
    assert result["rejected"] == []


def test_handle_events_oversized_event_id_rejected() -> None:
    conn = init_db(":memory:")
    payload = {"events": [_event("x" * 401)]}
    result = handle_events(payload, conn)
    assert result["ok"] is False
    assert result["rejected"] == ["x" * 401]
    assert result["accepted"] == 0


def test_handle_events_payload_without_events_list() -> None:
    conn = init_db(":memory:")
    result = handle_events({"events": "not-a-list"}, conn)
    assert result["ok"] is False
    assert result["rejected"] == []


def _post(port: int, path: str, body: str, method: str = "POST") -> tuple[int, dict]:
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        client.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = client.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data
    finally:
        client.close()


def _wait_until_accepting(port: int, attempts: int = 100) -> None:
    """轮询真实 TCP 连接直到 server 就绪，避免 accept 循环启动前的竞态。"""
    for _ in range(attempts):
        try:
            probe = socket.create_connection(("127.0.0.1", port), timeout=1)
            probe.close()
            return
        except OSError:
            time.sleep(0.02)
    raise AssertionError(f"server on port {port} 未在预期时间内就绪")


def test_events_server_http_endpoints() -> None:
    conn = init_db(":memory:", check_same_thread=False)
    server = events_server(port=0, conn=conn)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wait_until_accepting(port)
        status, data = _post(port, "/api/events", json.dumps({"events": [_event("srv-1")]}))
        assert status == 200
        assert data["ok"] is True
        assert data["accepted"] == 1

        status, data = _post(port, "/api/events", "not-json{{")
        assert status == 400
        assert data["ok"] is False

        status, _ = _post(port, "/api/events", "", method="GET")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
