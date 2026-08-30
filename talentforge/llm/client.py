"""OpenAI 兼容单 provider 客户端（M1）。

约定（prompt-cache，仿 OpenBiliClaw）：system 必须是模块级静态常量，
一切变量放 user message——system 随调用变化会击穿 provider 缓存。
配置链（优先级从高到低，M8 起文件层优先于 env）：
  1. 构造参数 base_url/api_key/model
  2. 设置文件 data/llm_settings.json（M8 设置页保存；路径 env
     TALENTFORGE_LLM_SETTINGS_PATH 可覆盖）——用户在 UI 显式保存的配置
     胜过作为部署种子的 env（优先级变更说明见 llm.settings）
  3. 环境变量 TALENTFORGE_LLM_BASE_URL / TALENTFORGE_LLM_API_KEY / TALENTFORGE_LLM_MODEL
  4. 回退：OpenCode 本地凭据（~/.local/share/opencode/auth.json，先 zhipuai-coding-plan
     的 GLM（glm-5.3 @ coding/paas/v4，deepseek 欠费后切换），后 deepseek.key；
     仅当未显式配置时读取；key 不落本项目任何文件）
解析统一走 llm.settings.effective_client_settings（逐字段回退，允许混搭）。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Protocol

import httpx

from talentforge.llm.settings import effective_client_settings, same_origin_host

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
        eff_base, eff_key, eff_model = effective_client_settings()
        self._base_url = (base_url or eff_base).rstrip("/")
        self._model = model or eff_model
        # 凭据只发往它配置时指向的主机：显式 base 与生效 base 不同主机且未给 key → 不回退生效 key
        if api_key or not base_url or same_origin_host(base_url, eff_base):
            self._api_key = api_key or eff_key
        else:
            self._api_key = ""
        self._transport = transport
        self._timeout = timeout

    async def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        """单轮对话；空 content（思考模型偶发只出 reasoning 不出答案）自动重试一次。

        max_tokens 供连通性探针等廉价调用限长（缺省不限制，常规对话不传）。
        """
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
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            for attempt in (1, 2):
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]
                content = raw if isinstance(raw, str) else ""
                if content.strip() or attempt == 2:
                    return content
                logger.info("LLM 空 content（attempt %s），重试一次", attempt)
        return ""  # 不可达：循环末轮必 return
