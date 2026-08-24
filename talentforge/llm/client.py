"""OpenAI 兼容单 provider 客户端（M1）。

约定（prompt-cache，仿 OpenBiliClaw）：system 必须是模块级静态常量，
一切变量放 user message——system 随调用变化会击穿 provider 缓存。
配置链（优先级从高到低）：
  1. 构造参数 base_url/api_key/model
  2. 环境变量 TALENTFORGE_LLM_BASE_URL / TALENTFORGE_LLM_API_KEY / TALENTFORGE_LLM_MODEL
  3. 回退：OpenCode 本地凭据（~/.local/share/opencode/auth.json，先 zhipuai-coding-plan
     的 GLM（glm-5.3 @ coding/paas/v4，deepseek 欠费后切换），后 deepseek.key；
     仅当未显式配置时读取；key 不落本项目任何文件）
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

_OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL = "deepseek-chat"
_ZHIPU_CODING_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
_ZHIPU_CODING_MODEL = "glm-5.3"


def _read_opencode_auth() -> dict:
    """读 OpenCode 凭据文件（只读；缺失/损坏返回空 dict）。"""
    try:
        data = json.loads(_OPENCODE_AUTH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_opencode_credentials() -> tuple[str, str, str]:
    """从 OpenCode 本地凭据解析 (base_url, api_key, model)。

    优先级：zhipuai-coding-plan（GLM-5.3，coding 专用端点）> deepseek.key；
    仅读取不做写入；无可用凭据返回空三元组。
    """
    data = _read_opencode_auth()
    zp = data.get("zhipuai-coding-plan") or {}
    if isinstance(zp, dict) and str(zp.get("key", "")):
        return (_ZHIPU_CODING_BASE_URL, str(zp["key"]), _ZHIPU_CODING_MODEL)
    ds = data.get("deepseek") or {}
    if isinstance(ds, dict):
        key = str(ds.get("key", ""))
        if key:
            return (_DEEPSEEK_BASE_URL, key, _DEEPSEEK_MODEL)
    return "", "", ""


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
        fallback_base, fallback_key, fallback_model = resolve_opencode_credentials()
        self._base_url = (base_url or env_base or fallback_base).rstrip("/")
        self._api_key = api_key or env_key or fallback_key
        self._model = model or env_model or fallback_model
        self._transport = transport
        self._timeout = timeout

    async def chat(self, system: str, user: str) -> str:
        """单轮对话；空 content（思考模型偶发只出 reasoning 不出答案）自动重试一次。"""
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
            for attempt in (1, 2):
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                content = str(data["choices"][0]["message"]["content"])
                if content.strip() or attempt == 2:
                    return content
                logger.info("LLM 空 content（attempt %s），重试一次", attempt)
        return ""  # 不可达：循环末轮必 return
