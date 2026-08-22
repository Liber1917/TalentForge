"""平台源路由测试：GET /api/sources 状态直出、凭据保存（不泄漏原值）、verify 启发判定。

凭据注入方式：monkeypatch cookies 模块级 CREDENTIALS_FILE / BOSS_COOKIE_FILE 指向
tmp_path（与 test_boss_scraper.py 对 BOSS_COOKIE_FILE 的注入方式一致，最小侵入）。
verify 外呼经 routes_sources._VERIFY_TRANSPORT 注入 httpx.MockTransport 伪造响应。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from talentforge.api import routes_sources
from talentforge.api.app import create_app
from talentforge.sources import cookies as cookies_module
from talentforge.sources.cookies import mask_cookie
from talentforge.storage.db import init_db

RAW_COOKIE = "wt2=abcdef1234567890wxyz; wbg=deadbeef9876"


def _make_client(monkeypatch: Any, tmp_path: Path) -> TestClient:
    """内存库应用 + env/凭据文件/jobclaw 文件全部指向可控位置。"""
    monkeypatch.delenv("TALENTFORGE_BOSS_COOKIE", raising=False)
    monkeypatch.setattr(cookies_module, "CREDENTIALS_FILE", tmp_path / "credentials.json")
    monkeypatch.setattr(cookies_module, "BOSS_COOKIE_FILE", tmp_path / "boss.json")
    conn = init_db(":memory:", check_same_thread=False)
    return TestClient(create_app(conn=conn))


def _boss_status(client: TestClient) -> dict:
    sources = client.get("/api/sources").json()["sources"]
    return next(s for s in sources if s["key"] == "boss")["status"]


def _mock_handler(status: int = 200, headers: dict[str, str] | None = None):
    """构造返回固定状态/头的 MockTransport handler。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers or {})

    return handler


def _verify_client(monkeypatch: Any, tmp_path: Path, handler) -> TestClient:
    """已保存 cookie + 注入伪造 transport 的客户端（verify 不打真实网络）。"""
    client = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(routes_sources, "_VERIFY_TRANSPORT", httpx.MockTransport(handler))
    response = client.post("/api/sources/boss/credential", json={"cookie": RAW_COOKIE})
    assert response.status_code == 200
    return client


# ---------- GET /api/sources ----------

def test_get_sources_lists_four_entries(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    response = client.get("/api/sources")
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert [s["key"] for s in sources] == ["boss", "bilibili", "zhihu", "github"]
    by_key = {s["key"]: s for s in sources}
    assert by_key["boss"]["kind"] == "cookie"
    assert by_key["bilibili"]["kind"] == "extension"
    assert by_key["zhihu"]["kind"] == "extension"
    assert by_key["github"]["kind"] == "public"
    assert by_key["boss"]["status"] == {"source": "none", "masked": ""}
    assert by_key["bilibili"]["status"] == {"source": "extension", "masked": ""}
    assert by_key["github"]["status"] == {"source": "public", "masked": ""}
    assert "TALENTFORGE_BOSS_COOKIE" in by_key["boss"]["note"]
    assert "无需配置" in by_key["bilibili"]["note"]
    assert "公开" in by_key["github"]["note"]
    assert by_key["boss"]["home"] == "https://www.zhipin.com/"
    assert by_key["bilibili"]["home"] == "https://www.bilibili.com/"
    assert by_key["zhihu"]["home"] == "https://www.zhihu.com/"
    assert by_key["github"]["home"] == "https://github.com/"
    assert by_key["boss"]["nav"] == "self"
    assert by_key["bilibili"]["nav"] == "blank"
    assert by_key["github"]["nav"] == "blank"


def test_save_credential_then_get_reflects_saved_without_leak(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    response = client.post("/api/sources/boss/credential", json={"cookie": RAW_COOKIE})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["status"]["source"] == "saved"
    assert data["status"]["masked"] == "wt2=****9876"

    status = _boss_status(client)
    assert status["source"] == "saved"
    assert status["masked"] == "wt2=****9876"

    whole = client.get("/api/sources").text
    assert "abcdef1234567890" not in whole, "原始 cookie 不得回传页面"
    assert "deadbeef" not in whole


def test_empty_cookie_does_not_overwrite(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    client.post("/api/sources/boss/credential", json={"cookie": RAW_COOKIE})
    before = (tmp_path / "credentials.json").read_text(encoding="utf-8")

    response = client.post("/api/sources/boss/credential", json={"cookie": ""})
    assert response.status_code == 200
    assert response.json()["status"]["source"] == "saved"
    assert response.json()["status"]["masked"] == "wt2=****9876"
    assert (tmp_path / "credentials.json").read_text(encoding="utf-8") == before


def test_credential_missing_or_non_string_returns_400(
    monkeypatch: Any, tmp_path: Path
) -> None:
    client = _make_client(monkeypatch, tmp_path)
    assert client.post("/api/sources/boss/credential", json={}).status_code == 400
    assert client.post("/api/sources/boss/credential", json={"cookie": 123}).status_code == 400


def test_env_overrides_saved_layer(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    client.post("/api/sources/boss/credential", json={"cookie": RAW_COOKIE})
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=envsecretvalue123")
    status = _boss_status(client)
    assert status["source"] == "env"
    assert status["masked"] == "wt2=****e123"


# ---------- POST /api/sources/boss/verify ----------

def test_verify_ok_on_200(monkeypatch: Any, tmp_path: Path) -> None:
    client = _verify_client(monkeypatch, tmp_path, _mock_handler(200))
    response = client.post("/api/sources/boss/verify")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": "连接正常"}


def test_verify_invalid_on_redirect_or_forbidden(monkeypatch: Any, tmp_path: Path) -> None:
    redirected = _verify_client(
        monkeypatch, tmp_path,
        _mock_handler(302, headers={"location": "https://www.zhipin.com/passport/login"}),
    )
    data = redirected.post("/api/sources/boss/verify").json()
    assert data["ok"] is False
    assert "失效" in data["detail"]

    forbidden = _verify_client(monkeypatch, tmp_path, _mock_handler(403))
    data = forbidden.post("/api/sources/boss/verify").json()
    assert data["ok"] is False
    assert "失效" in data["detail"]


def test_verify_invalid_on_set_cookie_clearing(monkeypatch: Any, tmp_path: Path) -> None:
    cleared = _verify_client(
        monkeypatch, tmp_path,
        _mock_handler(200, headers={"set-cookie": "wt2=; Expires=Thu, 01 Jan 1970 00:00:00 GMT"}),
    )
    data = cleared.post("/api/sources/boss/verify").json()
    assert data["ok"] is False
    assert "清除" in data["detail"]


def test_verify_timeout_returns_ok_false_not_500(monkeypatch: Any, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("连接超时")

    client = _verify_client(monkeypatch, tmp_path, handler)
    response = client.post("/api/sources/boss/verify")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["detail"].startswith("网络错误")


def test_verify_without_cookie_prompts_config_first(monkeypatch: Any, tmp_path: Path) -> None:
    client = _make_client(monkeypatch, tmp_path)
    response = client.post("/api/sources/boss/verify")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "尚未配置" in data["detail"]


# ---------- cookies.py 新增纯函数 ----------

def test_mask_cookie_rules() -> None:
    assert mask_cookie("") == ""
    assert mask_cookie("   ") == ""
    assert mask_cookie("abcdwxyz") == "********"
    assert mask_cookie("short") == "********"
    assert mask_cookie("abcd****wxyz"[0:4] + "middletext" + "wxyz") == "abcd****wxyz"
    assert mask_cookie("  abcdefghijklmnop  ") == "abcd****mnop"


def test_saved_file_preserves_other_keys(monkeypatch: Any, tmp_path: Path) -> None:
    cred = tmp_path / "credentials.json"
    cred.write_text(json.dumps({"github_token": "ghp_keepme"}), encoding="utf-8")
    monkeypatch.setattr(cookies_module, "CREDENTIALS_FILE", cred)
    cookies_module.save_boss_cookie("wt2=abc123def456")
    data = json.loads(cred.read_text(encoding="utf-8"))
    assert data["github_token"] == "ghp_keepme"
    assert data["boss_cookie"] == "wt2=abc123def456"


def test_load_boss_cookies_prefers_env_over_saved(monkeypatch: Any, tmp_path: Path) -> None:
    cred = tmp_path / "credentials.json"
    cred.write_text(json.dumps({"boss_cookie": "wt2=savedlayer123"}), encoding="utf-8")
    monkeypatch.setattr(cookies_module, "CREDENTIALS_FILE", cred)
    monkeypatch.setattr(cookies_module, "BOSS_COOKIE_FILE", tmp_path / "absent.json")

    monkeypatch.delenv("TALENTFORGE_BOSS_COOKIE", raising=False)
    cookies = cookies_module.load_boss_cookies()
    assert [(c["name"], c["value"]) for c in cookies] == [("wt2", "savedlayer123")]

    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=envlayer1234")
    cookies = cookies_module.load_boss_cookies()
    assert [(c["name"], c["value"]) for c in cookies] == [("wt2", "envlayer1234")]
