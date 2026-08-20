"""OpenAI 兼容单 provider 客户端（M1）。

约定（prompt-cache，仿 OpenBiliClaw）：system 必须是模块级静态常量，
一切变量放 user message——system 随调用变化会击穿 provider 缓存。
配置：TALENTFORGE_LLM_BASE_URL / TALENTFORGE_LLM_API_KEY / TALENTFORGE_LLM_MODEL。
"""
from __future__ import annotations

import os
from typing import Protocol

import httpx


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
        self._base_url = (base_url or os.environ.get("TALENTFORGE_LLM_BASE_URL", "")).rstrip("/")
        self._api_key = api_key or os.environ.get("TALENTFORGE_LLM_API_KEY", "")
        self._model = model or os.environ.get("TALENTFORGE_LLM_MODEL", "")
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
