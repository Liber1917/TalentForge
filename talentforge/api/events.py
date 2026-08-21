"""最小事件接收 API：handle_events + 单端点 stdlib HTTP 服务器（M3 换 FastAPI 时契约不变）。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from talentforge.storage.db import DEFAULT_DB_PATH, init_db, insert_event

EVENT_REQUIRED: tuple[str, ...] = ("event_id", "type", "url", "source_platform")

MAX_EVENT_ID_LEN = 400


def _invalid_reason(event: object, index: int) -> str | None:
    """返回事件无效时的 rejected 记录（无效即等于该记录），有效返回 None。"""
    if not isinstance(event, dict):
        return f"invalid:{index}"
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not 1 <= len(event_id.strip()) <= MAX_EVENT_ID_LEN:
        return f"invalid:{index}"
    for field in EVENT_REQUIRED[1:]:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"invalid:{index}"
    return None


def _rejected_label(event: object, index: int) -> str:
    """事件无效时的 rejected 记录：有 event_id 记 event_id，否则 invalid:<index>。"""
    if isinstance(event, dict):
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id.strip():
            return event_id
    return f"invalid:{index}"


def _now_iso() -> str:
    """当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _to_json(value: object) -> str:
    """把 context/metadata 序列化为 JSON 字符串，缺失返回空串。"""
    return json.dumps(value, ensure_ascii=False) if value is not None else ""


def handle_events(payload: dict, conn: sqlite3.Connection) -> dict:
    """逐条校验并入库 events 列表（幂等，event_id 主键去重）。

    无效事件进 rejected（记录 event_id 或 invalid:<index>）；有效事件
    INSERT OR IGNORE → accepted+1 / duplicates+1。返回
    {"ok": bool, "accepted": n, "duplicates": m, "rejected": [...]}，
    ok = len(rejected) == 0。
    """
    events = payload.get("events")
    if not isinstance(events, list):
        return {"ok": False, "accepted": 0, "duplicates": 0, "rejected": []}
    accepted = 0
    duplicates = 0
    rejected: list[str] = []
    for index, event in enumerate(events):
        if _invalid_reason(event, index) is not None:
            rejected.append(_rejected_label(event, index))
            continue
        event_id = event["event_id"].strip()
        title = event.get("title")
        inserted = insert_event(
            conn,
            event_id=event_id,
            event_type=event["type"].strip(),
            url=event["url"].strip(),
            title=title.strip() if isinstance(title, str) else "",
            source_platform=event["source_platform"].strip(),
            context_json=_to_json(event.get("context")),
            metadata_json=_to_json(event.get("metadata")),
            received_at=_now_iso(),
        )
        if inserted:
            accepted += 1
        else:
            duplicates += 1
    return {
        "ok": len(rejected) == 0,
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected": rejected,
    }


class EventsHandler(BaseHTTPRequestHandler):
    """处理 /api/events POST 的最小 handler（conn 由 events_server 注入）。"""

    conn: sqlite3.Connection
    server_version = "TalentForgeEvents/0.1"

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length > 0 else b""
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/events":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        payload = self._read_body()
        if payload is None:
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return
        result = handle_events(payload, self.conn)
        self._send_json(200 if result["ok"] else 400, result)

    def do_GET(self) -> None:
        self._send_json(404, {"ok": False, "error": "not found"})


def events_server(
    host: str = "127.0.0.1",
    port: int = 8420,
    conn: sqlite3.Connection | None = None,
) -> ThreadingHTTPServer:
    """启动最小事件接收 HTTP 服务器（stdlib ThreadingHTTPServer，零新依赖）。

    POST /api/events → handle_events → 200 {"ok":true,...} 或 400；其他路径/方法 404。
    conn 默认 init_db(DEFAULT_DB_PATH, check_same_thread=False)（server 生命周期内
    持有、多线程共享）。调用方负责 serve_forever / shutdown。
    """
    if conn is None:
        conn = init_db(DEFAULT_DB_PATH, check_same_thread=False)
    EventsHandler.conn = conn
    return ThreadingHTTPServer((host, port), EventsHandler)
