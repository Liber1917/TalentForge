"""OpenAI 兼容单 provider 客户端（M1）。

约定（prompt-cache，仿 OpenBiliClaw）：system 必须是模块级静态常量，
一切变量放 user message——system 随调用变化会击穿 provider 缓存。
配置链（优先级从高到低）：
  1. 构造参数 base_url/api_key/model
  2. 环境变量 TALENTFORGE_LLM_BASE_URL / TALENTFORGE_LLM_API_KEY / TALENTFORGE_LLM_MODEL
  3. 回退：OpenCode 本地凭据（~/.local/share/opencode/auth.json 的 deepseek.key，
     仅当未显式配置时读取；key 不落本项目任何文件）
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

import httpx

_OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL = "deepseek-chat"


def resolve_opencode_credentials() -> tuple[str, str]:
    """从 OpenCode 本地凭据解析 deepseek 的 (base_url, api_key)。

    仅读取，不做任何写入；文件缺失/结构不符返回空对。
    """
    try:
        data = json.loads(_OPENCODE_AUTH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    ds = data.get("deepseek") or {}
    if not isinstance(ds, dict):
        return "", ""
    key = str(ds.get("key", ""))
    return (_DEEPSEEK_BASE_URL, key) if key else ("", "")


class LLMClient(Protocol):
    async def chat(self, system: str, user: str) -> str: ...


class EnvLLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        env_base = os.environ.get("TALENTFORGE_LLM_BASE_URL", "")
        env_key = os.environ.get("TALENTFORGE_LLM_API_KEY", "")
        env_model = os.environ.get("TALENTFORGE_LLM_MODEL", "")
        fallback_base, fallback_key = resolve_opencode_credentials()
        self._base_url = (base_url or env_base or fallback_base).rstrip("/")
        self._api_key = api_key or env_key or fallback_key
        self._model = model or env_model or _DEEPSEEK_MODEL
        self._transport = transport
        self._timeout = timeout

    async def chat(self, system: str, user: str) -> str:
        if not self._base_url or not self._model:
            raise RuntimeError("LLM 未配置：需 TALENTFORGE_LLM_BASE_URL / TALENTFORGE_LLM_MODEL")
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        return str(data["choices"][0]["message"]["content"])
