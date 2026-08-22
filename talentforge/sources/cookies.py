"""Boss直聘登录 cookie 装载（env 原始串 > 页面保存层 > jobclaw cookie 文件 > 报错提示）.

格式对齐 jobclaw/auth/browser_login.py 的产物：
~/.jobclaw/cookies/boss.json = {"saved_at": float, "cookies": [Playwright cookie dict, ...]}。

页面保存层（OpenBiliClaw 平台源设计）：data/credentials.json 的 "boss_cookie" 键，
由 POST /api/sources/boss/credential 写入。注意 env ``TALENTFORGE_BOSS_COOKIE``
优先于页面保存层——env 已设时页面保存不生效（便于 CI/脚本强制覆盖）。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BOSS_COOKIE_DOMAIN = ".zhipin.com"
BOSS_COOKIE_PATH = "/"
BOSS_COOKIE_FILE = Path.home() / ".jobclaw" / "cookies" / "boss.json"

# 页面保存层凭据文件（相对 cwd，同 storage/db.py 的 DEFAULT_DB_PATH 风格；data/ 已 gitignore）
CREDENTIALS_FILE = Path("data/credentials.json")

ENV_COOKIE_VAR = "TALENTFORGE_BOSS_COOKIE"


class BossCookieNotFoundError(RuntimeError):
    """env 与 cookie 文件都找不到 Boss直聘登录 cookie 时抛出。"""


def parse_cookie_string(raw: str) -> list[dict[str, str]]:
    """把原始 cookie 串 ``"wt2=xxx; wbg=yyy"`` 解析成 Playwright cookie dict 列表。

    容忍分号两侧空白与空片段；无 ``=`` 的片段跳过。
    """
    cookies: list[dict[str, str]] = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": BOSS_COOKIE_DOMAIN,
                "path": BOSS_COOKIE_PATH,
            }
        )
    return cookies


def _env_raw() -> str:
    """读 env 原始 cookie 串（去空白；未设返回空串）。"""
    return os.environ.get(ENV_COOKIE_VAR, "").strip()


def _saved_raw() -> str:
    """读页面保存层 data/credentials.json 的 boss_cookie（缺失/损坏返回空串并告警）。"""
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        if isinstance(e, json.JSONDecodeError) or CREDENTIALS_FILE.exists():
            logger.warning("读取凭据文件 %s 失败: %s", CREDENTIALS_FILE, e)
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("boss_cookie", "")).strip()


def _jobclaw_cookies() -> list[dict[str, str]]:
    """读 jobclaw cookie 文件（缺失/无效返回空列表，沿用容错 + 日志）。"""
    if not BOSS_COOKIE_FILE.exists():
        return []
    try:
        data = json.loads(BOSS_COOKIE_FILE.read_text(encoding="utf-8"))
        cookies = data.get("cookies", data)
        if isinstance(cookies, list) and cookies:
            return cookies
        logger.warning("cookie 文件 %s 中无有效 cookies 数组", BOSS_COOKIE_FILE)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("读取 cookie 文件 %s 失败: %s", BOSS_COOKIE_FILE, e)
    return []


def mask_cookie(raw: str) -> str:
    """凭据脱敏：前4后4（如 ``abcd****wxyz``）；长度≤8 全掩码；空串保持空。

    页面只拿掩码摘要，后端永不回传原始 cookie（无"复制原值"入口）。
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "********"
    return f"{text[:4]}****{text[-4:]}"


def resolve_boss_raw() -> tuple[str, str]:
    """按优先级解析当前生效的 Boss cookie：返回 ``(source, 原始串)``。

    source ∈ env|saved|jobclaw|none；jobclaw 层无原始串，重构为
    ``name=value; ...`` 形式（verify 外呼用）；none 时原始串为空。
    """
    raw = _env_raw()
    if raw:
        return "env", raw
    raw = _saved_raw()
    if raw:
        return "saved", raw
    cookies = _jobclaw_cookies()
    if cookies:
        joined = "; ".join(
            f"{c.get('name', '')}={c.get('value', '')}" for c in cookies if isinstance(c, dict)
        )
        if joined.replace("=", "").replace(";", "").strip():
            return "jobclaw", joined
    return "none", ""


def get_boss_cookie_summary() -> dict[str, str]:
    """Boss 接入状态摘要：{source: env|saved|jobclaw|none, masked: 掩码串}。

    绝不返回原始值——只给前4后4掩码（无凭据时 masked 为空串）。
    """
    source, raw = resolve_boss_raw()
    return {"source": source, "masked": mask_cookie(raw)}


def save_boss_cookie(raw: str) -> None:
    """写入页面保存层 data/credentials.json 的 boss_cookie 键（保留其他键）。

    空串保存无意义且危险（会清掉现值）——留空=不覆盖的语义由路由层处理，
    这里对空白串直接抛 ValueError。
    """
    cleaned = str(raw).strip()
    if not cleaned:
        raise ValueError("cookie 为空：留空保存表示不覆盖现有值，不会写入")
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data["boss_cookie"] = cleaned
    CREDENTIALS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_boss_cookies() -> list[dict[str, str]]:
    """四层优先装载 Boss直聘 cookie，返回 Playwright cookie dict 列表。

    1. env ``TALENTFORGE_BOSS_COOKIE``（原始 cookie 串；已设时页面保存层不生效）；
    2. ``data/credentials.json`` 的 boss_cookie（页面保存层）；
    3. ``~/.jobclaw/cookies/boss.json`` 的 cookies 数组（jobclaw 登录产物）；
    4. 都没有 → raise BossCookieNotFoundError（附 README 配置提示）。
    """
    source, raw = resolve_boss_raw()
    if source in ("env", "saved"):
        cookies = parse_cookie_string(raw)
        if cookies:
            return cookies
    elif source == "jobclaw":
        cookies = _jobclaw_cookies()
        if cookies:
            return cookies

    raise BossCookieNotFoundError(
        "未找到 Boss直聘登录 cookie：请先按 README 配置 cookie"
        f"（设置 {ENV_COOKIE_VAR} 原始 cookie 串，或在「平台源」页面粘贴保存，"
        f"或经 jobclaw 登录生成 {BOSS_COOKIE_FILE}）"
    )
