"""LLM 连接设置存储（M8 Web 配置化）：文件层 data/llm_settings.json。

设计参考 OpenBiliClaw 设置卡（与 sources.cookies 页面保存层同构）：
- api_key 落盘明文（本地工具，文件在 gitignored data/ 下）但**永不回传明文**——
  读回只给前4后4掩码（复用 sources.cookies.mask_cookie）；
- 留空保存不覆盖：api_key 空串/缺省 = 保持现值（敏感值读回是掩码，用户无法
  原样重填，同 /api/sources/boss/credential 语义）；
- 生效优先级（M8 起，**env 让位文件**）：构造参数 > 设置文件 > env
  （TALENTFORGE_LLM_BASE_URL/API_KEY/MODEL）> OpenCode auth 回退。
  优先级变更理由：文件是用户在 Web UI 显式保存的配置，应胜过作为部署种子的
  env——已用 env 部署的用户不受影响（不保存文件即维持 env 生效）；
- 路径 env TALENTFORGE_LLM_SETTINGS_PATH 覆盖（同 api.common.profile_path
  的 env 覆盖写法；写链永不落 git 跟踪文件，data/ 已 gitignore）。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from talentforge.sources.cookies import mask_cookie

logger = logging.getLogger(__name__)

SETTINGS_ENV = "TALENTFORGE_LLM_SETTINGS_PATH"
RUNTIME_SETTINGS_PATH = Path("data/llm_settings.json")  # 相对 cwd（data/ 已 gitignore）

_ENV_BASE = "TALENTFORGE_LLM_BASE_URL"
_ENV_KEY = "TALENTFORGE_LLM_API_KEY"
_ENV_MODEL = "TALENTFORGE_LLM_MODEL"
_ENV_CONCURRENCY = "TALENTFORGE_MATCH_CONCURRENCY"
_DEFAULT_CONCURRENCY = 5


class LLMSettings(BaseModel):
    """LLM 连接设置（单 provider，OpenAI 兼容端点）。"""

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    match_concurrency: int = 5


def settings_path() -> Path:
    """设置文件路径：env TALENTFORGE_LLM_SETTINGS_PATH > 运行时 data/llm_settings.json。"""
    env = os.environ.get(SETTINGS_ENV)
    return Path(env) if env else RUNTIME_SETTINGS_PATH


class LLMSettingsStore:
    """load/save/masked 三件套（无状态薄封装，路径每次经 settings_path() 解析）。"""

    def load(self) -> LLMSettings:
        """读设置文件；缺失/损坏/字段校验失败 → 全默认（损坏告警，不抛错）。"""
        path = settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if isinstance(exc, json.JSONDecodeError) or path.exists():
                logger.warning("读取 LLM 设置文件 %s 失败: %s", path, exc)
            return LLMSettings()
        if not isinstance(data, dict):
            logger.warning("LLM 设置文件 %s 结构异常（非对象），按默认处理", path)
            return LLMSettings()
        try:
            return LLMSettings.model_validate(data)
        except ValidationError as exc:
            logger.warning("LLM 设置文件 %s 字段校验失败，按默认处理: %s", path, exc)
            return LLMSettings()

    def has_saved(self) -> bool:
        """设置文件是否存在（区分「文件显式并发」与「无文件回退 env」两级）。"""
        return settings_path().exists()

    def save(self, partial: dict) -> LLMSettings:
        """merge 写回设置文件，返回保存后的完整设置。

        语义（partial 为调用方筛过的「已提交字段」dict）：
        - api_key：空串/缺省 = 不覆盖（掩码读回导致用户无法原样重填）；
        - base_url/model：键存在即覆盖（非敏感、明文读回，清空即恢复回退链）；
        - match_concurrency：int 且 ≥1 才覆盖。
        """
        data = self.load().model_dump()
        if isinstance(partial.get("base_url"), str):
            data["base_url"] = partial["base_url"].strip()
        if isinstance(partial.get("model"), str):
            data["model"] = partial["model"].strip()
        api_key = partial.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            data["api_key"] = api_key.strip()
        concurrency = partial.get("match_concurrency")
        if isinstance(concurrency, int) and concurrency >= 1:
            data["match_concurrency"] = concurrency
        settings = LLMSettings.model_validate(data)
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(settings.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return settings

    def masked(self, settings: LLMSettings | None = None) -> dict:
        """读回视图：api_key 只给前4后4掩码（mask_cookie 规则），其余字段原样。

        永不回传明文 api_key——无"复制原值"入口。
        """
        view = settings if settings is not None else self.load()
        return {
            "base_url": view.base_url,
            "api_key": mask_cookie(view.api_key),
            "model": view.model,
            "match_concurrency": view.match_concurrency,
        }


def effective_settings() -> tuple[LLMSettings, str]:
    """解析当前生效配置与来源：逐字段 文件 > env > OpenCode auth 回退。

    返回 ``(生效设置, source)``；source ∈ ``file|env|fallback|none``——取贡献了
    任意生效字段的最高层（全部未配置 = none）。逐字段回退允许「文件补
    base_url/model、key 走 env/回退」的混搭（与 client.py 旧链的逐字段语义
    一致）。优先级变更（M8）见模块 docstring：文件 > env——旧链 env > 回退
    中未含文件层，env 部署不受影响（不保存文件即维持 env）。
    """
    from talentforge.llm.client import resolve_opencode_credentials  # 延迟导入避免 client↔settings 环

    saved = LLMSettingsStore().load()
    env_base = os.environ.get(_ENV_BASE, "").strip()
    env_key = os.environ.get(_ENV_KEY, "").strip()
    env_model = os.environ.get(_ENV_MODEL, "").strip()
    fb_base, fb_key, fb_model = resolve_opencode_credentials()
    base = saved.base_url.strip() or env_base or fb_base
    key = saved.api_key.strip() or env_key or fb_key
    model = saved.model.strip() or env_model or fb_model
    if saved.base_url.strip() or saved.api_key.strip() or saved.model.strip():
        source = "file"
    elif env_base or env_key or env_model:
        source = "env"
    elif fb_base or fb_key or fb_model:
        source = "fallback"
    else:
        source = "none"
    return (
        LLMSettings(
            base_url=base, api_key=key, model=model, match_concurrency=saved.match_concurrency
        ),
        source,
    )


def effective_match_concurrency() -> int:
    """决策匹配并发度：设置文件（≥1）> env TALENTFORGE_MATCH_CONCURRENCY > 5。

    旧实现（generate.MATCH_CONCURRENCY 模块级常量）import 时固化 env，设置页
    改并发需重启才生效——这里每次调用现解析（M8）。env 非整数回退 5
    （旧实现 import 即崩，这里优雅降级）。
    """
    store = LLMSettingsStore()
    if store.has_saved():
        value = store.load().match_concurrency
        if value >= 1:
            return value
    try:
        return max(1, int(os.environ.get(_ENV_CONCURRENCY, str(_DEFAULT_CONCURRENCY))))
    except ValueError:
        return _DEFAULT_CONCURRENCY


def effective_client_settings() -> tuple[str, str, str]:
    """EnvLLMClient 解析入口：生效 (base_url, api_key, model)，优先级见 effective_settings。"""
    settings, _source = effective_settings()
    return settings.base_url, settings.api_key, settings.model
