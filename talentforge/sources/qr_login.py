"""Boss 扫码登录会话（持久化浏览器 Profile + 二维码截屏 + 登录态轮询）。

为什么不用 DevTools/复制 cookie：Boss 的 disable-devtool 会检测并关闭页面，
用户侧取 cookie 困难；改为服务器开浏览器（已注入 stealth 层）→ 登录页二维码
截图 → 用户手机 Boss App 扫码 → 轮询登录态 → cookie 直接落本机。

- launchPersistentContext + data/boss-profile：登录态持久，二次登录免扫；
- cookie 落库走 sources.cookies.save_boss_cookie（页面保存层，env 优先级不变）；
- 单会话模型：同一时间最多一个登录会话（本地工具，够用）。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from talentforge.sources.boss_scraper import USER_AGENT
from talentforge.sources.cookies import save_boss_cookie
from talentforge.sources.stealth import LAUNCH_ARGS, apply_stealth

logger = logging.getLogger(__name__)

LOGIN_URL = "https://www.zhipin.com/web/user/?ka=header-login"
PROFILE_DIR = Path("data/boss-profile")
# 登录页默认停在"验证码登录"tab，需点击"APP扫码登录"切换（实测 2026-08：不点则二维码不渲染）
QR_TAB_SELECTOR = ".btn-sign-switch.ewm-switch"
QR_SIZE_RANGE = (100, 400)  # 二维码元素按尺寸识别（class 不稳定）
# 登录成功的判定 cookie（Boss 登录态核心字段）
LOGIN_COOKIE_KEYS = ("wt2", "wbg", "bst")
POLL_INTERVAL_S = 2.0
SESSION_TIMEOUT_S = 300.0

_FIND_QR_JS = """() => {
  const el = [...document.querySelectorAll('img, canvas')].find((e) => {
    const r = e.getBoundingClientRect();
    return r.width > 100 && r.width < 400 && r.height > 100 && r.height < 400;
  });
  return el || null;
}"""

_CLICK_QR_TAB_JS = """() => {
  const el = document.querySelector('.btn-sign-switch.ewm-switch')
    || [...document.querySelectorAll('div')].find((e) => e.textContent.trim() === 'APP扫码登录');
  if (el) el.click();
  return !!el;
}"""


class QrLoginSession:
    """单次扫码登录会话：start → qr_png（轮询刷新）→ 状态机 waiting/success/failed。"""

    def __init__(self, headless: bool | None = None) -> None:
        self._headless = (
            os.environ.get("TALENTFORGE_HEADLESS", "true").strip().lower() not in ("0", "false", "no")
            if headless is None
            else headless
        )
        self.state = "starting"
        self.error = ""
        self._qr_png_b64 = ""
        self._qr_updated_at = datetime.now(timezone.utc)
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """起持久化浏览器到登录页，后台任务轮询登录态（超时 5 分钟自动 failed）。"""
        try:
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=self._headless,
                args=list(LAUNCH_ARGS),
                user_agent=USER_AGENT,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            apply_stealth(self._context)
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            await self._page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            await self._page.wait_for_timeout(4_000)
            await self._page.evaluate(_CLICK_QR_TAB_JS)
            await self._refresh_qr()
            self.state = "waiting"
            self._task = asyncio.create_task(self._poll_loop())
        except Exception as exc:  # noqa: BLE001 — 会话级兜底：任何启动失败都转 failed 状态
            logger.warning("扫码登录会话启动失败: %s", exc)
            self.error = f"启动失败：{exc}"
            self.state = "failed"
            await self.close()

    async def _refresh_qr(self) -> None:
        """截图二维码元素为 PNG base64。

        按尺寸（100–400px）定位二维码元素（class 不稳定）；页面被关或元素
        未出现时重导航登录页并点扫码 tab 一次后重试；仍失败整页截图兜底。
        """
        if self._page is None:
            return
        handle = await self._page.evaluate_handle(_FIND_QR_JS)
        el = handle.as_element()
        if el is None:
            if self._page.url.startswith("about:"):
                await self._page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            else:
                await self._page.evaluate(_CLICK_QR_TAB_JS)
            await self._page.wait_for_timeout(3_000)
            handle = await self._page.evaluate_handle(_FIND_QR_JS)
            el = handle.as_element()
        try:
            if el is not None:
                png = await el.screenshot()
            else:
                png = await self._page.screenshot()
        except Exception:  # noqa: BLE001 — 元素在截图瞬间消失等边缘情况，整页兜底
            png = await self._page.screenshot()
        self._qr_png_b64 = base64.b64encode(png).decode("ascii")
        self._qr_updated_at = datetime.now(timezone.utc)

    async def _poll_loop(self) -> None:
        """轮询登录态：命中登录 cookie → 落库转 success；超时 → failed。"""
        deadline = asyncio.get_event_loop().time() + SESSION_TIMEOUT_S
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(POLL_INTERVAL_S)
            if self._context is None:
                return
            try:
                cookies = await self._context.cookies()
            except Exception:  # noqa: BLE001 — 浏览器被关等异常直接结束轮询
                return
            if any(c["name"] in LOGIN_COOKIE_KEYS for c in cookies):
                raw = "; ".join(f"{c['name']}={c['value']}" for c in cookies if "zhipin" in c["domain"])
                try:
                    save_boss_cookie(raw)
                    self.state = "success"
                except OSError as exc:
                    self.error = f"cookie 落盘失败：{exc}"
                    self.state = "failed"
                await self.close()
                return
            # 二维码约 2 分钟过期：定期重截（重导航/点 tab 由 _refresh_qr 内部处理）
            if (datetime.now(timezone.utc) - self._qr_updated_at).total_seconds() > 90:
                await self._refresh_qr()
        self.error = "超时未扫码（5 分钟）"
        self.state = "failed"
        await self.close()

    def qr_png_b64(self) -> str:
        """当前二维码 PNG 的 base64（前端 <img src="data:image/png;base64,...">）。"""
        return self._qr_png_b64

    def status(self) -> dict[str, str]:
        """会话状态快照。"""
        return {"state": self.state, "error": self.error}

    async def close(self) -> None:
        """关浏览器与后台任务（幂等）。"""
        if self._task and not self._task.done():
            self._task.cancel()
        if self._context:
            try:
                await self._context.close()
            except Exception:  # noqa: BLE001 — 关闭异常不影响状态
                pass
            self._context = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None


_current: QrLoginSession | None = None


async def start_session(headless: bool | None = None) -> QrLoginSession:
    """启动（或复用）唯一扫码登录会话。"""
    global _current
    if _current and _current.state in ("starting", "waiting"):
        return _current
    _current = QrLoginSession(headless=headless)
    await _current.start()
    return _current


def current_session() -> QrLoginSession | None:
    """当前会话（无会话返回 None）。"""
    return _current
