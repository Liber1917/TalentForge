"""Boss Playwright 抓取循环测试（全程 mock，不启动真实浏览器）。

fake playwright/browser/context/page 链：page.content() 返回 Task 1 fixture HTML，
page.inner_text("body") 默认空串（验证码用例改写）。页间随机延迟 patch 为 0。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import talentforge.sources.boss_scraper as boss_scraper_module
import talentforge.sources.cookies as cookies_module
from talentforge.sources.boss_scraper import BossScraper, CaptchaDetectedError
from talentforge.sources.cookies import BossCookieNotFoundError, load_boss_cookies

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "talentforge" / "sources" / "fixtures"
FIXTURE_PATH = FIXTURES_DIR / "boss_search_page.html"


class FakePage:
    """记录 goto 调用；content/inner_text 返回预设值。"""

    def __init__(self, html: str, body_text: str = "") -> None:
        self.goto_calls: list[dict[str, Any]] = []
        self._html = html
        self._body_text = body_text

    async def goto(self, url: str, wait_until: str = "", timeout: int = 0) -> None:
        self.goto_calls.append({"url": url, "wait_until": wait_until, "timeout": timeout})

    async def content(self) -> str:
        return self._html

    async def inner_text(self, selector: str) -> str:
        assert selector == "body"
        return self._body_text


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self._page = page
        self.add_cookies_calls: list[list[dict[str, str]]] = []
        self.closed = False

    async def add_cookies(self, cookies: list[dict[str, str]]) -> None:
        self.add_cookies_calls.append(cookies)

    async def new_page(self) -> FakePage:
        return self._page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self._context = context
        self.launch_kwargs: dict[str, Any] = {}
        self.context_kwargs: list[dict[str, Any]] = []
        self.closed = False

    async def new_context(self, **kwargs: Any) -> FakeContext:
        self.context_kwargs.append(kwargs)
        return self._context

    async def close(self) -> None:
        self.closed = True


class FakePlaywright:
    def __init__(self, browser: FakeBrowser) -> None:
        self._browser = browser
        self.stopped = False

    @property
    def chromium(self) -> FakePlaywright:
        return self

    async def start(self) -> FakePlaywright:
        return self

    async def launch(self, **kwargs: Any) -> FakeBrowser:
        self._browser.launch_kwargs = kwargs
        return self._browser

    async def stop(self) -> None:
        self.stopped = True


def _install_fake(
    monkeypatch: pytest.MonkeyPatch, html: str, body_text: str = ""
) -> tuple[FakePage, FakeContext, FakeBrowser]:
    """把 fake playwright 链装进 boss_scraper 模块，并把随机延迟 patch 为 0。"""
    page = FakePage(html, body_text)
    context = FakeContext(page)
    browser = FakeBrowser(context)
    monkeypatch.setattr(boss_scraper_module, "async_playwright", lambda: FakePlaywright(browser))
    monkeypatch.setattr(boss_scraper_module.random, "uniform", lambda a, b: 0.0)
    return page, context, browser


async def test_scrape_two_pages_paginates_and_accumulates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2 页抓取：goto 恰好 2 次、URL 含城市码、5 卡×2=10 个 Job。

    本层不做跨页去重（fixture 两页相同 → 同 href 各出现一次，共 10 个）；
    同 URL 去重是 storage 层（upsert）的职责。
    """
    _install_fake(monkeypatch, FIXTURE_PATH.read_text(encoding="utf-8"))
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=abc; wbg=def")

    async with BossScraper() as scraper:
        jobs = await scraper.scrape("后端工程师", "深圳", limit=20, pages=2)

    page = scraper._browser.context_kwargs  # noqa: SLF001 — 仅断言用
    assert len(page) == 2  # 每页新建 context
    assert len(jobs) == 10
    assert all(job.source == "boss" for job in jobs)
    assert all(job.location == "深圳" for job in jobs)
    assert len({job.url for job in jobs}) == 5  # 两页同 fixture，层内不去重


async def test_scrape_goto_urls_carry_city_code_and_wait_opts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_page, _, _ = _install_fake(monkeypatch, FIXTURE_PATH.read_text(encoding="utf-8"))
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=abc")

    async with BossScraper() as scraper:
        await scraper.scrape("后端工程师", "深圳", limit=20, pages=2)

    assert len(fake_page.goto_calls) == 2
    assert all("city=101280600" in call["url"] for call in fake_page.goto_calls)
    assert [call["url"].split("page=")[1] for call in fake_page.goto_calls] == ["1", "2"]
    assert all(call["wait_until"] == "networkidle" for call in fake_page.goto_calls)
    assert all(call["timeout"] == 30_000 for call in fake_page.goto_calls)


async def test_scrape_early_stops_when_limit_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """limit=5 时第 1 页即凑满 → 不再 goto 第 2 页。"""
    fake_page, _, _ = _install_fake(monkeypatch, FIXTURE_PATH.read_text(encoding="utf-8"))
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=abc")

    async with BossScraper() as scraper:
        jobs = await scraper.scrape("后端工程师", "深圳", limit=5, pages=3)

    assert len(fake_page.goto_calls) == 1
    assert len(jobs) == 5


async def test_cookie_injection_uses_zhipin_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    _, fake_context, _ = _install_fake(monkeypatch, FIXTURE_PATH.read_text(encoding="utf-8"))
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=abc; wbg=def")

    async with BossScraper() as scraper:
        await scraper.scrape("后端工程师", "深圳", limit=5, pages=1)

    assert fake_context.add_cookies_calls, "add_cookies 应被调用"
    injected = fake_context.add_cookies_calls[0]
    assert {c["name"] for c in injected} == {"wt2", "wbg"}
    assert all(c["domain"] == ".zhipin.com" for c in injected)


async def test_salary_translated_to_annual_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """25-50K·16薪 → min_annual=400000 / max_annual=800000；无薪资卡为 None。"""
    _install_fake(monkeypatch, FIXTURE_PATH.read_text(encoding="utf-8"))
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=abc")

    async with BossScraper() as scraper:
        jobs = await scraper.scrape("后端工程师", "深圳", limit=20, pages=1)

    by_title = {job.title: job for job in jobs}
    assert by_title["Python 后端工程师"].salary is not None
    assert by_title["Python 后端工程师"].salary.min_annual == 400_000
    assert by_title["Python 后端工程师"].salary.max_annual == 800_000
    assert by_title["Python 后端工程师"].salary.currency == "CNY"
    no_salary = [job for job in jobs if "无薪资展示" in job.title]
    assert len(no_salary) == 1 and no_salary[0].salary is None


async def test_captcha_page_raises_captcha_detected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(
        monkeypatch, "<html><body>请完成安全验证</body></html>", body_text="请完成安全验证"
    )
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=abc")

    async with BossScraper() as scraper:
        with pytest.raises(CaptchaDetectedError) as exc_info:
            await scraper.scrape("后端工程师", "深圳", limit=20, pages=2)

    assert "1" in str(exc_info.value)  # 附页码
    assert "安全验证" in str(exc_info.value)


async def test_cookie_injection_failure_does_not_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """cookie 完全缺失 → 仅 warning，抓取继续（照抄 jobclaw 容错）。"""
    monkeypatch.delenv("TALENTFORGE_BOSS_COOKIE", raising=False)
    monkeypatch.setattr(
        cookies_module, "BOSS_COOKIE_FILE", Path("/nonexistent/.jobclaw/cookies/boss.json")
    )
    _install_fake(monkeypatch, FIXTURE_PATH.read_text(encoding="utf-8"))

    async with BossScraper() as scraper:
        jobs = await scraper.scrape("后端工程师", "深圳", limit=20, pages=1)

    assert len(jobs) == 5


def test_env_cookie_string_parses_to_playwright_dicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "wt2=abc; wbg=def")
    cookies = load_boss_cookies()
    assert len(cookies) == 2
    assert cookies[0] == {
        "name": "wt2",
        "value": "abc",
        "domain": ".zhipin.com",
        "path": "/",
    }
    assert cookies[1]["name"] == "wbg"
    assert cookies[1]["value"] == "def"
    assert cookies[1]["domain"] == ".zhipin.com"


def test_env_cookie_string_tolerates_messy_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALENTFORGE_BOSS_COOKIE", "  wt2 = abc ; ; wbg=def ; broken ")
    cookies = load_boss_cookies()
    assert [(c["name"], c["value"]) for c in cookies] == [("wt2", "abc"), ("wbg", "def")]


def test_load_boss_cookies_from_jobclaw_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """jobclaw 登录产物格式 {"saved_at": float, "cookies": [...]} 直接复用。"""
    import json

    monkeypatch.delenv("TALENTFORGE_BOSS_COOKIE", raising=False)
    cookie_file = tmp_path / "boss.json"
    cookie_file.write_text(
        json.dumps(
            {
                "saved_at": 1_700_000_000.0,
                "cookies": [{"name": "wt2", "value": "x", "domain": ".zhipin.com", "path": "/"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cookies_module, "BOSS_COOKIE_FILE", cookie_file)
    assert load_boss_cookies() == [
        {"name": "wt2", "value": "x", "domain": ".zhipin.com", "path": "/"}
    ]


def test_load_boss_cookies_raises_with_hint_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TALENTFORGE_BOSS_COOKIE", raising=False)
    monkeypatch.setattr(cookies_module, "BOSS_COOKIE_FILE", tmp_path / "absent.json")
    with pytest.raises(BossCookieNotFoundError, match="README"):
        load_boss_cookies()
