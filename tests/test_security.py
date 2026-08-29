"""M10 安全批次测试：凭据加密 / 明文迁移 / Origin 校验 / /api/debug 移除。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.security.crypto import decrypt_value, encrypt_value, is_encrypted


# ---------------- crypto 单元 ----------------


def test_encrypt_decrypt_roundtrip(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("TALENTFORGE_SECRET_KEY_FILE", str(tmp_path / "key.bin"))
    token = encrypt_value("sk-secret-1234")
    assert token != "sk-secret-1234"
    assert token.startswith("gAAAAA")
    assert decrypt_value(token) == "sk-secret-1234"
    assert is_encrypted(token)


def test_decrypt_legacy_plaintext_passthrough(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("TALENTFORGE_SECRET_KEY_FILE", str(tmp_path / "key.bin"))
    # 遗留明文（旧版本未加密）→ 解密原样返回，不抛错
    assert decrypt_value("sk-legacy-plain") == "sk-legacy-plain"
    assert is_encrypted("sk-legacy-plain") is False
    assert decrypt_value("") == ""
    assert encrypt_value("") == ""


def test_key_created_with_0600_permissions(tmp_path: Path, monkeypatch: Any) -> None:
    import talentforge.security.crypto as crypto

    key_path = tmp_path / "key.bin"
    monkeypatch.setenv("TALENTFORGE_SECRET_KEY_FILE", str(key_path))
    crypto._fernet = None  # reset 模块级单例，强制按新 env 生成密钥
    encrypt_value("x")
    assert key_path.exists()
    mode = os.stat(key_path).st_mode & 0o777
    assert mode == 0o600


# ---------------- settings.py 加密落盘 ----------------


def test_llm_settings_api_key_encrypted_at_rest(tmp_path: Path, monkeypatch: Any) -> None:
    from talentforge.llm.settings import LLMSettingsStore

    path = tmp_path / "llm.json"
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(path))
    monkeypatch.setenv("TALENTFORGE_SECRET_KEY_FILE", str(tmp_path / "key.bin"))
    store = LLMSettingsStore()
    store.save({"api_key": "sk-supersecret"})
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["api_key"].startswith("gAAAAA")  # 落盘是密文
    assert "sk-supersecret" not in path.read_text(encoding="utf-8")
    assert store.load().api_key == "sk-supersecret"  # 读回解密


# ---------------- Origin 校验中间件 ----------------


def _client(tmp_path: Path, monkeypatch: Any) -> TestClient:
    from talentforge.storage.db import init_db

    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(tmp_path / "llm.json"))
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials", lambda: ("", "", "")
    )
    return TestClient(create_app(conn=init_db(":memory:")))


def test_origin_guard_rejects_foreign_origin(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(tmp_path, monkeypatch)
    resp = client.get(
        "/api/health",
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_origin_guard_allows_localhost_origin(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(tmp_path, monkeypatch)
    resp = client.get(
        "/api/health",
        headers={"Origin": "http://127.0.0.1:8420"},
    )
    assert resp.status_code == 200


def test_origin_guard_allows_no_origin(tmp_path: Path, monkeypatch: Any) -> None:
    # 无 Origin 头（curl / 扩展 fetch / 同源导航）放行
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/api/health")
    assert resp.status_code == 200


# ---------------- /api/debug 已移除 ----------------


def test_debug_endpoint_removed(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/debug", json={"kind": "test"})
    # 404=路由不存在；405=静态挂载兜底对 POST 的方法拒绝——两者都证明 /api/debug 端点已删
    assert resp.status_code in (404, 405)


# ---------------- 扩展事件上报放行（M10 修正：采集平台域） ----------------


def test_events_allows_platform_origins(tmp_path: Path, monkeypatch: Any) -> None:
    """扩展 content script 在 zhipin/bilibili/zhihu 页面内上报 → 必须放行（采集链路）。"""
    client = _client(tmp_path, monkeypatch)
    for origin in (
        "https://www.zhipin.com",
        "https://www.bilibili.com",
        "https://www.zhihu.com",
    ):
        resp = client.post(
            "/api/events", headers={"Origin": origin}, json={"events": []}
        )
        assert resp.status_code in (200, 400), f"{origin} 应放行到事件端点"


def test_events_still_blocks_evil_origins(tmp_path: Path, monkeypatch: Any) -> None:
    """恶意站点 Origin 即使打 /api/events 也拒绝；平台域打其他端点同样拒绝。"""
    client = _client(tmp_path, monkeypatch)
    evil_events = client.post(
        "/api/events", headers={"Origin": "https://evil.example.com"}, json={"events": []}
    )
    assert evil_events.status_code == 403
    platform_other = client.get(
        "/api/health", headers={"Origin": "https://www.bilibili.com"}
    )
    assert platform_other.status_code == 403
