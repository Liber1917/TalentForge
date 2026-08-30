"""LLM 连接设置路由（M8）：GET/POST /api/llm/settings + POST /api/llm/settings/verify。

设计参考 OpenBiliClaw 设置卡 + 本项目 routes_sources 凭据模式：
- GET 只回掩码 api_key（前4后4，永不回传明文），附当前生效来源 source
  （file|env|fallback|none）供前端展示"当前在用哪套配置"；
- POST merge 保存：api_key 空串/缺省 = 不覆盖（掩码读回导致用户无法原样重填）；
- verify 用提交的（或已存）配置真实外呼一次 chat（max_tokens=8 廉价 ping），
  返回 ok + latency_ms；网络失败优雅降级 ok=False 不 500（同 routes_sources.verify）。
- 测试经 _VERIFY_TRANSPORT 注入 httpx.MockTransport 伪造响应，不打真实网络。
"""

from __future__ import annotations

import logging
import time

import httpx
from fastapi import APIRouter, HTTPException

from talentforge.llm.client import EnvLLMClient
from talentforge.llm.settings import LLMSettingsStore, effective_settings, same_origin_host

logger = logging.getLogger(__name__)

router = APIRouter(tags=["llm"])

# verify 外呼参数（测试注入 MockTransport；与 routes_sources._VERIFY_TRANSPORT 同构）
_VERIFY_TRANSPORT: httpx.AsyncBaseTransport | None = None
_VERIFY_TIMEOUT: float = 20.0
_VERIFY_MAX_TOKENS: int = 8


@router.get("/api/llm/settings")
def get_llm_settings() -> dict:
    """读回当前配置（掩码视图）+ 生效来源。"""
    effective, source = effective_settings()
    store = LLMSettingsStore()
    return {
        "ok": True,
        "settings": store.masked(effective),
        "source": source,
    }


@router.post("/api/llm/settings")
def save_llm_settings(body: dict) -> dict:
    """merge 保存设置；返回掩码视图（api_key 空 = 不覆盖语义，同 sources/boss/credential）。"""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="需要 JSON 对象")
    unknown = set(body) - {"base_url", "api_key", "model", "match_concurrency"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知字段: {sorted(unknown)}")
    # 类型校验前置（save 内部宽容，非法类型直接忽略会产生"静默不生效"）
    for field in ("base_url", "api_key", "model"):
        if field in body and not isinstance(body[field], str):
            raise HTTPException(status_code=400, detail=f"{field} 需要字符串")
    if "match_concurrency" in body and (
        not isinstance(body["match_concurrency"], int) or body["match_concurrency"] < 1
    ):
        raise HTTPException(status_code=400, detail="match_concurrency 需要 ≥1 的整数")
    store = LLMSettingsStore()
    try:
        settings = store.save(body)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"设置文件写入失败：{exc}") from exc
    return {"ok": True, "settings": store.masked(settings)}


@router.post("/api/llm/settings/verify")
async def verify_llm_settings(body: dict | None = None) -> dict:
    """用提交配置（或已存配置）真实外呼一次短对话验证连通性。

    body 为空 / 字段缺省 = 用当前已存（effective）配置；提交字段 = 临时用该配置
    （不落盘，与保存分离——用户可先测后存）。凭据不回传。
    """
    body = body or {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="需要 JSON 对象")
    store = LLMSettingsStore()
    effective, _source = effective_settings()
    # 临时合并提交字段（仅本次 verify 生效，不保存）
    base_url = body.get("base_url", effective.base_url) or ""
    model = body.get("model", effective.model) or ""
    api_key = str(body.get("api_key") or "")
    # key 只跟随同主机的已存配置：提交陌生主机 base 必须自带 key（防凭据转发外泄）
    if not api_key and same_origin_host(base_url, effective.base_url):
        api_key = effective.api_key
    if not base_url or not model:
        return {"ok": False, "detail": "未配置 base_url / model：请先填写再测试"}
    client = EnvLLMClient(
        base_url=base_url,
        api_key=api_key or None,
        model=model,
        transport=_VERIFY_TRANSPORT,
        timeout=_VERIFY_TIMEOUT,
    )
    started = time.perf_counter()
    try:
        content = await client.chat(
            "你是连通性测试助手。", "请只回复 ok。", max_tokens=_VERIFY_MAX_TOKENS
        )
    except (httpx.HTTPError, KeyError, ValueError, RuntimeError) as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "detail": f"连接失败：{exc}", "latency_ms": latency_ms}
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not content.strip():
        return {"ok": False, "detail": "连接成功但返回为空", "latency_ms": latency_ms}
    return {"ok": True, "detail": "连接正常", "latency_ms": latency_ms}
