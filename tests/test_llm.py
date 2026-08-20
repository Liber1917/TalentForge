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
