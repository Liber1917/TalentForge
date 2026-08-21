"""Boss直聘 抓取核心（纯函数层：城市码表 / 搜索 URL / 卡片解析 / 薪资归一化）.

上游参考 jobclaw/scraper/boss.py（MIT），修正其坑：
城市码硬编码改为码表、单选择器改为回退链、薪资统一年薪口径。
"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup, Tag

CITY_CODES: dict[str, str] = {
    "深圳": "101280600",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "西安": "101110100",
    "南京": "101190100",
    "长沙": "101250100",
}

SEARCH_URL_BASE = "https://www.zhipin.com/web/geek/job"

CARD_SELECTORS: list[str] = [
    ".job-card-wrapper",
    ".job-card-box",
    "li.job-card",
    "ul.job-list-box li",
    "[ka^='search_list_']",
]

TITLE_SELECTORS: list[str] = [".job-name", ".job-title"]
COMPANY_SELECTORS: list[str] = [".company-name a", ".company-name"]
SALARY_SELECTORS: list[str] = [".salary", ".job-salary"]
LINK_SELECTORS: list[str] = [".job-card-left a", "a[href*='/job_detail/']"]
TAG_SELECTORS: list[str] = [".tag-list span", ".job-tags span", ".tag-list li"]
DESC_SELECTORS: list[str] = [".job-card-desc", ".job-desc"]

_SALARY_RANGE_RE = re.compile(r"(\d+)-(\d+)[kK]")
_SALARY_MONTHS_RE = re.compile(r"(\d+)薪")


def build_search_url(query: str, city: str, page: int = 1) -> str:
    """构建 Boss直聘职位搜索页 URL。

    city 接受中文城市名（经 CITY_CODES 映射为城市码）或直接传城市码；
    query 中文自动百分号编码。
    """
    city_code = CITY_CODES.get(city, city)
    params = urlencode({"query": query, "city": city_code, "page": page})
    return f"{SEARCH_URL_BASE}?{params}"


def parse_salary(text: str) -> dict[str, int | str]:
    """解析 Boss 薪资文本为年薪口径 dict。

    "25-50K·16薪" → {"min_annual": 400000, "max_annual": 800000, "currency": "CNY"}；
    奖金月数缺省按 12 薪；无法匹配时返回空 dict。
    """
    range_match = _SALARY_RANGE_RE.search(text)
    if not range_match:
        return {}
    low_k = int(range_match.group(1))
    high_k = int(range_match.group(2))
    months = 12
    months_match = _SALARY_MONTHS_RE.search(text)
    if months_match:
        months = int(months_match.group(1))
    return {
        "min_annual": low_k * 1000 * months,
        "max_annual": high_k * 1000 * months,
        "currency": "CNY",
    }


def _first_text(card: Tag, selectors: list[str]) -> str:
    for selector in selectors:
        el = card.select_one(selector)
        if el is None:
            continue
        text = el.get_text(strip=True)
        if text:
            return text
    return ""


def _first_href(card: Tag, selectors: list[str]) -> str:
    for selector in selectors:
        el = card.select_one(selector)
        if el is not None:
            href = el.get("href", "")
            if href:
                return str(href)
    return ""


def _first_tags(card: Tag, selectors: list[str]) -> list[str]:
    for selector in selectors:
        texts = [el.get_text(strip=True) for el in card.select(selector)]
        texts = [text for text in texts if text]
        if texts:
            return texts
    return []


def parse_boss_cards(
    html: str, base_url: str = "https://www.zhipin.com"
) -> list[dict[str, object]]:
    """解析 Boss直聘搜索页 HTML，返回职位卡原始字段列表。

    卡片与字段均走选择器回退链以兼容多版页面结构；无标题的解析失败卡跳过；
    相同链接的卡按最终 URL 去重。返回 dict 字段：
    title / company / salary_text / tags / href / description（均为原始文本）。
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[Tag] = []
    seen_elements: set[int] = set()
    for selector in CARD_SELECTORS:
        for el in soup.select(selector):
            if id(el) not in seen_elements:
                seen_elements.add(id(el))
                candidates.append(el)

    def _has_candidate_ancestor(el: Tag) -> bool:
        return any(id(parent) in seen_elements for parent in el.parents)

    card_els = [el for el in candidates if not _has_candidate_ancestor(el)]

    cards: list[dict[str, object]] = []
    seen_hrefs: set[str] = set()
    for el in card_els:
        title = _first_text(el, TITLE_SELECTORS)
        if not title:
            continue
        href_raw = _first_href(el, LINK_SELECTORS)
        href = urljoin(base_url, href_raw) if href_raw else ""
        if href and href in seen_hrefs:
            continue
        if href:
            seen_hrefs.add(href)
        cards.append(
            {
                "title": title,
                "company": _first_text(el, COMPANY_SELECTORS),
                "salary_text": _first_text(el, SALARY_SELECTORS),
                "tags": _first_tags(el, TAG_SELECTORS),
                "href": href,
                "description": _first_text(el, DESC_SELECTORS),
            }
        )
    return cards
