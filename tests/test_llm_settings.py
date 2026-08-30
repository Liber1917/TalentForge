"""LLM 设置路由与存储测试（M8）：优先级、掩码、不覆盖语义、verify 注入。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from talentforge.api.app import create_app
from talentforge.api import routes_llm
from talentforge.llm import settings as llm_settings
from talentforge.llm.settings import LLMSettingsStore


@pytest.fixture
def store(tmp_path: Path, monkeypatch: Any) -> LLMSettingsStore:
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(tmp_path / "llm.json"))
    return LLMSettingsStore()


def _client(monkeypatch: Any, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(tmp_path / "llm.json"))
    # 隔离真实凭据回退：测试环境不读 OpenCode auth.json 的 GLM 凭据
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials", lambda: ("", "", "")
    )
    return TestClient(create_app())


# ---------------- 存储层：优先级 / 掩码 / 不覆盖 ----------------


def test_store_defaults_when_no_file(store: LLMSettingsStore) -> None:
    settings = store.load()
    assert settings.base_url == ""
    assert settings.api_key == ""
    assert settings.model == ""
    assert settings.match_concurrency == 5
    assert store.has_saved() is False


def test_store_save_merge_roundtrip(store: LLMSettingsStore) -> None:
    store.save({"base_url": "https://api.example.com/v1", "model": "gpt-x", "match_concurrency": 3})
    settings = store.load()
    assert settings.base_url == "https://api.example.com/v1"
    assert settings.model == "gpt-x"
    assert settings.match_concurrency == 3
    assert store.has_saved() is True


def test_store_empty_key_does_not_overwrite(store: LLMSettingsStore) -> None:
    store.save({"api_key": "sk-secret-123"})
    store.save({"api_key": "", "model": "m2"})
    settings = store.load()
    assert settings.api_key == "sk-secret-123"
    assert settings.model == "m2"


def test_store_masked_never_returns_plaintext(store: LLMSettingsStore) -> None:
    store.save({"api_key": "sk-secret-1234"})
    view = store.masked()
    assert view["api_key"] == "sk-s****234" or "****" in view["api_key"]
    assert "sk-secret-1234" not in view["api_key"]


def test_store_corrupt_file_falls_back_to_default(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "llm.json"
    path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(path))
    settings = LLMSettingsStore().load()
    assert settings.base_url == ""


# ---------------- effective_settings：文件 > env > 回退 ----------------


def test_effective_settings_file_beats_env(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "llm.json"
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(path))
    monkeypatch.setenv("TALENTFORGE_LLM_BASE_URL", "https://env.example.com/v1")
    monkeypatch.delenv("TALENTFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("TALENTFORGE_LLM_MODEL", raising=False)
    path.write_text(
        json.dumps({"base_url": "https://file.example.com/v1", "model": "file-model"}),
        encoding="utf-8",
    )
    settings, source = llm_settings.effective_settings()
    assert source == "file"
    assert settings.base_url == "https://file.example.com/v1"
    assert settings.model == "file-model"


def test_effective_settings_env_when_no_file(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setenv("TALENTFORGE_LLM_BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("TALENTFORGE_LLM_MODEL", "env-model")
    settings, source = llm_settings.effective_settings()
    assert source == "env"
    assert settings.base_url == "https://env.example.com/v1"


def test_effective_match_concurrency_from_file(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "llm.json"
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(path))
    monkeypatch.delenv("TALENTFORGE_MATCH_CONCURRENCY", raising=False)
    path.write_text(json.dumps({"match_concurrency": 3}), encoding="utf-8")
    assert llm_settings.effective_match_concurrency() == 3


# ---------------- API：GET/POST/verify ----------------


def test_get_settings_empty(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/llm/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["source"] in ("file", "env", "fallback", "none")
    assert data["settings"]["api_key"] == ""


def test_post_settings_merge_and_masked(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/llm/settings",
        json={"base_url": "https://api.example.com/v1", "api_key": "sk-topsecret-1234", "model": "m9"},
    )
    assert response.status_code == 200
    view = response.json()["settings"]
    assert view["base_url"] == "https://api.example.com/v1"
    assert view["model"] == "m9"
    assert "topsecret" not in json.dumps(view)


def test_post_settings_unknown_field_rejected(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/llm/settings", json={"bogus": 1})
    assert response.status_code == 400


def test_post_settings_bad_concurrency_rejected(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/llm/settings", json={"match_concurrency": 0})
    assert response.status_code == 400


def test_verify_success_with_mock_transport(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(routes_llm, "_VERIFY_TRANSPORT", httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    ))
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/llm/settings/verify",
        json={"base_url": "https://api.example.com/v1", "model": "m9"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["latency_ms"] >= 0


def test_verify_network_error_degrades(tmp_path: Path, monkeypatch: Any) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    monkeypatch.setattr(routes_llm, "_VERIFY_TRANSPORT", httpx.MockTransport(boom))
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/llm/settings/verify",
        json={"base_url": "https://api.example.com/v1", "model": "m9"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_verify_without_config_returns_friendly_failure(tmp_path: Path, monkeypatch: Any) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/llm/settings/verify", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "未配置" in data["detail"]


# ---------------- 安全：凭据不随陌生主机外发（外泄链封堵） ----------------


def _isolate_llm_env(monkeypatch: Any, tmp_path: Path) -> Path:
    """清空 env 三变量、指向 tmp 设置文件，返回设置文件路径。"""
    for var in ("TALENTFORGE_LLM_BASE_URL", "TALENTFORGE_LLM_API_KEY", "TALENTFORGE_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "llm.json"
    monkeypatch.setenv("TALENTFORGE_LLM_SETTINGS_PATH", str(path))
    return path


def test_fallback_key_not_attached_to_custom_base_url(tmp_path: Path, monkeypatch: Any) -> None:
    """文件存自定义 base（攻击者可经 POST /api/llm/settings 写入）时，
    OpenCode 回退 key 不得生效——否则本机凭据被发往任意端点。"""
    path = _isolate_llm_env(monkeypatch, tmp_path)
    path.write_text(
        json.dumps({"base_url": "https://evil.example.com/v1", "model": "m"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials",
        lambda: ("https://open.bigmodel.cn/api/coding/paas/v4", "fb-secret", "glm-5.3"),
    )
    settings, _source = llm_settings.effective_settings()
    assert settings.base_url == "https://evil.example.com/v1"
    assert settings.api_key == ""


def test_fallback_key_attached_when_base_is_official(tmp_path: Path, monkeypatch: Any) -> None:
    """回退 base（官方端点）配回退 key 的原有配对不受影响。"""
    _isolate_llm_env(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials",
        lambda: ("https://api.deepseek.com", "sk-fallback", "deepseek-chat"),
    )
    settings, source = llm_settings.effective_settings()
    assert source == "fallback"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.api_key == "sk-fallback"


def test_env_key_pairs_custom_base_unchanged(tmp_path: Path, monkeypatch: Any) -> None:
    """env key + 文件自定义 base = 用户部署种子自己的配对，不受影响。"""
    path = _isolate_llm_env(monkeypatch, tmp_path)
    monkeypatch.setenv("TALENTFORGE_LLM_API_KEY", "env-key")
    path.write_text(
        json.dumps({"base_url": "https://my-relay.example.com/v1", "model": "m"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials",
        lambda: ("https://api.deepseek.com", "sk-fallback", "deepseek-chat"),
    )
    settings, _source = llm_settings.effective_settings()
    assert settings.api_key == "env-key"


def _auth_capturing_transport(seen: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    return httpx.MockTransport(handler)


def test_verify_custom_base_does_not_inherit_stored_key(tmp_path: Path, monkeypatch: Any) -> None:
    """verify 提交陌生主机 base 且未提交 key：不得继承已存 key 外发。"""
    path = _isolate_llm_env(monkeypatch, tmp_path)
    path.write_text(
        json.dumps(
            {"base_url": "https://api.example.com/v1", "api_key": "sk-file-secret", "model": "m"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials", lambda: ("", "", "")
    )
    seen: dict = {}
    monkeypatch.setattr(routes_llm, "_VERIFY_TRANSPORT", _auth_capturing_transport(seen))
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/llm/settings/verify",
        json={"base_url": "https://evil.example.com/v1", "model": "m"},
    )
    assert response.status_code == 200
    assert seen.get("auth") in (None, "")


def test_verify_same_base_inherits_stored_key(tmp_path: Path, monkeypatch: Any) -> None:
    """verify 提交与已存同主机的 base：正常继承已存 key（合法配对）。"""
    path = _isolate_llm_env(monkeypatch, tmp_path)
    path.write_text(
        json.dumps(
            {"base_url": "https://api.example.com/v1", "api_key": "sk-file-secret", "model": "m"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "talentforge.llm.client.resolve_opencode_credentials", lambda: ("", "", "")
    )
    seen: dict = {}
    monkeypatch.setattr(routes_llm, "_VERIFY_TRANSPORT", _auth_capturing_transport(seen))
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/llm/settings/verify",
        json={"base_url": "https://api.example.com/v1", "model": "m"},
    )
    assert response.status_code == 200
    assert seen.get("auth") == "Bearer sk-file-secret"
