import json

import httpx
import pytest
from talentforge.llm.client import EnvLLMClient
from talentforge.llm.json_utils import extract_json

def _mock_client(payload: dict) -> EnvLLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    return EnvLLMClient(
        base_url="https://llm.test/v1", api_key="k", model="m",
        transport=httpx.MockTransport(handler),
    )

@pytest.mark.asyncio
async def test_chat_sends_static_system_and_dynamic_user():
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
    c = EnvLLMClient(base_url="https://l.test/v1", api_key="k", model="m",
                     transport=httpx.MockTransport(handler))
    out = await c.chat(system="STATIC", user="动态内容")
    assert out == "hi"
    msgs = seen["body"]["messages"]
    assert msgs[0] == {"role": "system", "content": "STATIC"}
    assert msgs[1]["role"] == "user"

def test_extract_json_direct():
    assert extract_json('{"a": 1}') == {"a": 1}

def test_extract_json_fenced():
    text = '说明如下\n```json\n{"dims": [1, 2]}\n```\n完'
    assert extract_json(text) == {"dims": [1, 2]}

def test_extract_json_wrapped():
    text = '结果是 {"x": "y"} 请查收'
    assert extract_json(text) == {"x": "y"}

def test_extract_json_garbage_raises():
    import pytest as _p
    with _p.raises(ValueError):
        extract_json("根本没有json")

# --- OpenCode 凭据回退链（R7 用户批准；M4 后 GLM 优先） ---


def test_resolve_opencode_credentials_prefers_zhipu_coding(tmp_path, monkeypatch):
    import talentforge.llm.client as client_mod

    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "zhipuai-coding-plan": {"type": "api", "key": "zp-key-123"},
                "deepseek": {"type": "api", "key": "sk-test-123"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", auth)
    base, key, model = client_mod.resolve_opencode_credentials()
    assert base == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert key == "zp-key-123"
    assert model == "glm-5.3"


def test_resolve_opencode_credentials_reads_deepseek_key(tmp_path, monkeypatch):
    import talentforge.llm.client as client_mod

    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"deepseek": {"type": "api", "key": "sk-test-123"}}), encoding="utf-8")
    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", auth)
    base, key, model = client_mod.resolve_opencode_credentials()
    assert base == "https://api.deepseek.com"
    assert key == "sk-test-123"
    assert model == "deepseek-chat"


def test_resolve_opencode_credentials_missing_file(tmp_path, monkeypatch):
    import talentforge.llm.client as client_mod

    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", tmp_path / "nope.json")
    assert client_mod.resolve_opencode_credentials() == ("", "", "")


def test_env_client_falls_back_to_opencode(tmp_path, monkeypatch):
    import talentforge.llm.client as client_mod

    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"deepseek": {"type": "api", "key": "sk-fallback"}}), encoding="utf-8")
    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", auth)
    for var in ("TALENTFORGE_LLM_BASE_URL", "TALENTFORGE_LLM_API_KEY", "TALENTFORGE_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    c = client_mod.EnvLLMClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert c._base_url == "https://api.deepseek.com"
    assert c._api_key == "sk-fallback"
    assert c._model == "deepseek-chat"


def test_env_client_explicit_overrides_everything(tmp_path, monkeypatch):
    import talentforge.llm.client as client_mod

    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", tmp_path / "missing.json")
    monkeypatch.setenv("TALENTFORGE_LLM_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("TALENTFORGE_LLM_API_KEY", "env-key")
    monkeypatch.setenv("TALENTFORGE_LLM_MODEL", "env-model")
    c = client_mod.EnvLLMClient(
        base_url="https://explicit.test/v1", api_key="explicit-key", model="explicit-model"
    )
    assert c._base_url == "https://explicit.test/v1"
    assert c._api_key == "explicit-key"
    assert c._model == "explicit-model"


def test_env_client_no_key_leak_across_hosts(tmp_path, monkeypatch):
    """凭据只发往它配置时指向的主机：显式 base 与生效 base 不同主机且未给 key
    → 不回退生效 key；同主机（含尾斜杠变体）正常继承。"""
    import talentforge.llm.client as client_mod

    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", tmp_path / "missing.json")
    monkeypatch.setenv("TALENTFORGE_LLM_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("TALENTFORGE_LLM_API_KEY", "env-key")
    monkeypatch.setenv("TALENTFORGE_LLM_MODEL", "env-model")

    cross = client_mod.EnvLLMClient(base_url="https://other.test/v1", model="m")
    assert cross._base_url == "https://other.test/v1"
    assert cross._api_key == ""

    same = client_mod.EnvLLMClient(base_url="https://env.test/v1/", model="m")
    assert same._api_key == "env-key"


def test_chat_retries_once_on_empty_content(tmp_path, monkeypatch):
    """空 content（思考模型偶发）自动重试一次，第二次有内容即返回（backlog 修复钉桩）。"""
    import httpx
    import talentforge.llm.client as client_mod

    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", tmp_path / "missing.json")
    monkeypatch.setenv("TALENTFORGE_LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("TALENTFORGE_LLM_API_KEY", "k")
    monkeypatch.setenv("TALENTFORGE_LLM_MODEL", "m")

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = "" if calls["n"] == 1 else "ok"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = client_mod.EnvLLMClient(transport=httpx.MockTransport(handler))

    import asyncio

    assert asyncio.run(client.chat("s", "u")) == "ok"
    assert calls["n"] == 2


def test_chat_returns_empty_after_second_empty(tmp_path, monkeypatch):
    """两轮都空则原样返回空串（不无限重试）。"""
    import asyncio

    import httpx
    import talentforge.llm.client as client_mod

    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", tmp_path / "missing.json")
    monkeypatch.setenv("TALENTFORGE_LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("TALENTFORGE_LLM_API_KEY", "k")
    monkeypatch.setenv("TALENTFORGE_LLM_MODEL", "m")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    client = client_mod.EnvLLMClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(client.chat("s", "u")) == ""
    assert calls["n"] == 2


def test_chat_null_content_treated_as_empty(tmp_path, monkeypatch):
    """思考模型只出 reasoning 时 API 返回 content=null：str(None)="None" 是
    truthy，会击穿空串重试并把字面量 "None" 送进 extract_json/决策链。
    null 必须按空处理（重试一次，仍空则返回空串）。"""
    import asyncio

    import httpx
    import talentforge.llm.client as client_mod

    monkeypatch.setattr(client_mod, "_OPENCODE_AUTH", tmp_path / "missing.json")
    monkeypatch.setenv("TALENTFORGE_LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("TALENTFORGE_LLM_API_KEY", "k")
    monkeypatch.setenv("TALENTFORGE_LLM_MODEL", "m")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    client = client_mod.EnvLLMClient(transport=httpx.MockTransport(handler))
    assert asyncio.run(client.chat("s", "u")) == ""
    assert calls["n"] == 2
