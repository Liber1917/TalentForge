"""Boss直聘 Playwright 抓取循环（浏览器层：cookie 注入 / 翻页 / 验证码暂停）.

上游参考 jobclaw/scraper/boss.py 的 async context manager 模式与 UA 伪装，
扩展：城市码翻页、页间随机延迟、验证码检测到即暂停报错（合规红线：不绕过）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import random

from playwright.async_api import Browser, Playwright, async_playwright

from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange
from talentforge.sources.boss import build_search_url, parse_boss_cards, parse_salary
from talentforge.sources.captcha import detect_captcha_keywords
from talentforge.sources.cookies import load_boss_cookies
from talentforge.sources.stealth import LAUNCH_ARGS, apply_stealth

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

PAGE_LOAD_TIMEOUT_MS = 30_000
PAGE_TURN_DELAY_RANGE = (5.0, 10.0)
_FALSY = {"0", "false", "no"}


class CaptchaDetectedError(RuntimeError):
    """页面文本命中验证码 / 安全拦截关键词时抛出（合规红线：检测到即暂停，不绕过）。"""


class BossScraper:
    """Boss直聘 Playwright 抓取器，仿 jobclaw 的 ``async with`` 生命周期。"""

    def __init__(self, headless: bool | None = None) -> None:
        """headless 为 None 时读 env ``TALENTFORGE_HEADLESS``（默认 true）。"""
        if headless is None:
            headless = os.environ.get("TALENTFORGE_HEADLESS", "true").strip().lower() not in _FALSY
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> BossScraper:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless, args=list(LAUNCH_ARGS)
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def scrape(self, query: str, city: str, limit: int = 20, pages: int = 3) -> list[Job]:
        """抓取 Boss直聘搜索结果并归一化为 ``Job`` 列表。

        每页：新建 context（UA 伪装）→ 注入 load_boss_cookies()（注入失败仅
        warning 不中断，照抄 jobclaw 容错）→ goto 搜索页（networkidle / 30s）→
        页面文本 detect_captcha_keywords 命中即 raise CaptchaDetectedError →
        parse_boss_cards(page.content()) 逐卡转 Job。累计达到 limit 提前停；
        翻页前 asyncio.sleep(random.uniform(5,10))，最后一页不睡。
        本层不做跨页去重（同 href 的 Job 由 storage 层按 URL 去重）。
        """
        if not self._browser:
            raise RuntimeError("BossScraper 未初始化，请使用 'async with' 上下文。")

        jobs: list[Job] = []
        for page_no in range(1, pages + 1):
            context = await self._browser.new_context(user_agent=USER_AGENT)
            apply_stealth(context)
            try:
                try:
                    await context.add_cookies(load_boss_cookies())
                except Exception as e:
                    logger.warning("Cookie 注入失败（继续未登录抓取）: %s", e)

                page = await context.new_page()
                await page.goto(
                    build_search_url(query, city, page_no),
                    wait_until="networkidle",
                    timeout=PAGE_LOAD_TIMEOUT_MS,
                )

                body_text = await page.inner_text("body")
                hits = detect_captcha_keywords(body_text)
                if hits:
                    raise CaptchaDetectedError(
                        f"第 {page_no} 页命中验证码关键词 {hits}："
                        "请在浏览器中完成安全验证后重试（合规红线：不自动绕过）"
                    )

                for card in parse_boss_cards(await page.content()):
                    jobs.append(self._card_to_job(card, city))
                    if len(jobs) >= limit:
                        break
            finally:
                await context.close()

            if len(jobs) >= limit:
                break
            if page_no < pages:
                await asyncio.sleep(random.uniform(*PAGE_TURN_DELAY_RANGE))

        logger.info("Boss: query=%r city=%r 共抓得 %d 个岗位", query, city, len(jobs))
        return jobs

    @staticmethod
    def _card_to_job(card: dict[str, object], city: str) -> Job:
        """原始卡 dict → 归一化 Job（parse_salary 转 SalaryRange，无薪资为 None）。"""
        salary_dict = parse_salary(str(card.get("salary_text", "")))
        return Job(
            source="boss",
            title=str(card.get("title", "")),
            company=str(card.get("company", "")),
            location=city,
            url=str(card.get("href", "")),
            description=str(card.get("description", "")),
            salary=SalaryRange(**salary_dict) if salary_dict else None,
            tags=[str(tag) for tag in card.get("tags", [])],
        )
