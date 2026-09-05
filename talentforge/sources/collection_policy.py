"""采集模式分级策略（D30/M11）：平台分档 + 日配额 + 冷却 + kill switch。

分档依据 docs/research/m11-platform-recon.md：
- auto 仅限"岗位事实"语义平台（zhaopin/shixiseng/liepin）；
- 行为类平台（bilibili/zhihu）红线 manual——自动访问=伪造用户显示性行为（D6/O1）；
- zhipin=assist（D25 封禁证据链 + 用户裁决"人在场主动浏览"）；
- lagou（平台 2026-05 破产）/linkedin（UA §8.2.2 点名浏览器插件 + 大陆不可达）禁入。
未知平台默认 blocked（显式禁入优先）。

覆盖文件 data/collection_policy.json（gitignored；env TALENTFORGE_COLLECTION_POLICY
可指路径）：{"paused": bool, "platforms": {platform: {mode/daily_quota/enabled}}}。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

POLICY_ENV = "TALENTFORGE_COLLECTION_POLICY"
RUNTIME_POLICY_PATH = Path("data/collection_policy.json")

MODE_MANUAL = "manual"
MODE_ASSIST = "assist"
MODE_AUTO = "auto"
MODE_BLOCKED = "blocked"

DEFAULT_DAILY_QUOTA = 20
COOLDOWN_MINUTES = 30
MAX_DWELL_MS = 30_000

DEFAULT_POLICY: dict[str, dict[str, Any]] = {
    "zhipin": {"mode": MODE_ASSIST},
    "bilibili": {"mode": MODE_MANUAL},
    "zhihu": {"mode": MODE_MANUAL},
    "zhaopin": {"mode": MODE_AUTO, "daily_quota": DEFAULT_DAILY_QUOTA},
    "shixiseng": {"mode": MODE_AUTO, "daily_quota": DEFAULT_DAILY_QUOTA},
    "liepin": {"mode": MODE_AUTO, "daily_quota": DEFAULT_DAILY_QUOTA},
    "lagou": {"mode": MODE_BLOCKED, "reason": "平台已破产（m11-platform-recon §四）"},
    "linkedin": {"mode": MODE_BLOCKED, "reason": "合规硬伤 + 大陆不可达（m11-platform-recon §五）"},
}


def policy_path() -> Path:
    env = os.environ.get(POLICY_ENV)
    return Path(env) if env else RUNTIME_POLICY_PATH


def load_policy(path: Path | None = None) -> dict[str, Any]:
    """读策略状态：JSON 损坏/缺失回落默认表（结构 {"paused", "platforms"}）。"""
    p = path or policy_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"paused": False, "platforms": DEFAULT_POLICY}
    if not isinstance(raw, dict):
        return {"paused": False, "platforms": DEFAULT_POLICY}
    platforms = {**DEFAULT_POLICY}
    overrides = raw.get("platforms")
    if isinstance(overrides, dict):
        for name, cfg in overrides.items():
            if isinstance(cfg, dict):
                platforms[name] = {**platforms.get(name, {}), **cfg}
    return {"paused": bool(raw.get("paused")), "platforms": platforms}


def mode_for(platform: str, policy: dict[str, Any] | None = None) -> str:
    state = policy if policy is not None else load_policy()
    platforms = state.get("platforms", DEFAULT_POLICY)
    entry = platforms.get(platform)
    mode = entry.get("mode") if isinstance(entry, dict) else None
    return mode if isinstance(mode, str) else MODE_BLOCKED


def daily_quota(platform: str, policy: dict[str, Any] | None = None) -> int:
    state = policy if policy is not None else load_policy()
    entry = state.get("platforms", {}).get(platform)
    quota = entry.get("daily_quota") if isinstance(entry, dict) else None
    return quota if isinstance(quota, int) and quota > 0 else DEFAULT_DAILY_QUOTA


def can_auto(platform: str, policy: dict[str, Any] | None = None) -> bool:
    """auto 准入 = 模式为 auto + 未全局暂停 + 平台未被禁用（kill switch）。"""
    state = policy if policy is not None else load_policy()
    if state.get("paused"):
        return False
    entry = state.get("platforms", {}).get(platform)
    if not isinstance(entry, dict):
        return False
    if entry.get("enabled") is False:
        return False
    return entry.get("mode") == MODE_AUTO
