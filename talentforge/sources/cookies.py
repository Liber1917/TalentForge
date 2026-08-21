"""Boss直聘登录 cookie 装载（env 原始串优先 > jobclaw cookie 文件 > 报错提示）.

格式对齐 jobclaw/auth/browser_login.py 的产物：
~/.jobclaw/cookies/boss.json = {"saved_at": float, "cookies": [Playwright cookie dict, ...]}。
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


def load_boss_cookies() -> list[dict[str, str]]:
    """三层优先装载 Boss直聘 cookie，返回 Playwright cookie dict 列表。

    1. env ``TALENTFORGE_BOSS_COOKIE``（原始 cookie 串）；
    2. ``~/.jobclaw/cookies/boss.json`` 的 cookies 数组（jobclaw 登录产物）；
    3. 都没有 → raise BossCookieNotFoundError（附 README 配置提示）。
    """
    raw = os.environ.get(ENV_COOKIE_VAR, "").strip()
    if raw:
        cookies = parse_cookie_string(raw)
        if cookies:
            return cookies

    if BOSS_COOKIE_FILE.exists():
        try:
            data = json.loads(BOSS_COOKIE_FILE.read_text(encoding="utf-8"))
            cookies = data.get("cookies", data)
            if isinstance(cookies, list) and cookies:
                return cookies
            logger.warning("cookie 文件 %s 中无有效 cookies 数组", BOSS_COOKIE_FILE)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("读取 cookie 文件 %s 失败: %s", BOSS_COOKIE_FILE, e)

    raise BossCookieNotFoundError(
        "未找到 Boss直聘登录 cookie：请先按 README 配置 cookie"
        f"（设置 {ENV_COOKIE_VAR} 原始 cookie 串，或经 jobclaw 登录生成 {BOSS_COOKIE_FILE}）"
    )
