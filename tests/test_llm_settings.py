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
