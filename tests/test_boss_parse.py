"""Boss 抓取纯函数层测试（fixture 解析 / 薪资归一化 / 城市码 / URL / 验证码检测）。"""

from __future__ import annotations

from pathlib import Path

from talentforge.sources.boss import CITY_CODES, build_search_url, parse_boss_cards, parse_salary
from talentforge.sources.captcha import detect_captcha_keywords

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "talentforge" / "sources" / "fixtures"
FIXTURE_PATH = FIXTURES_DIR / "boss_search_page.html"


def _load_fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_fixture_parses_five_cards_with_fallback_chain() -> None:
    cards = parse_boss_cards(_load_fixture())
    assert len(cards) == 5
    by_title = {str(card["title"]): card for card in cards}

    primary = by_title["Python 后端工程师"]
    assert primary["company"] == "星辰科技"
    assert primary["salary_text"] == "25-50K·16薪"
    assert primary["tags"] == ["Python", "分布式", "三年经验"]
    assert primary["description"]

    variant = by_title["Golang 基础架构工程师"]
    assert variant["company"] == "星环科技"
    assert variant["salary_text"] == "30-45K·14薪"
    assert variant["tags"] == ["Go", "K8s"]

    for card in cards:
        assert str(card["href"]).startswith("https://www.zhipin.com/")
        assert "/job_detail/" in str(card["href"])
        assert card["title"]
        assert card["company"]


def test_card_without_salary_does_not_crash() -> None:
    cards = parse_boss_cards(_load_fixture())
    no_salary = [card for card in cards if "无薪资展示" in str(card["title"])]
    assert len(no_salary) == 1
    assert no_salary[0]["salary_text"] == ""
    assert parse_salary(str(no_salary[0]["salary_text"])) == {}


def test_broken_card_without_title_is_skipped() -> None:
    html = """
    <ul>
      <li class="job-card-wrapper"><div class="tag-list"><span>Python</span></div></li>
      <li class="job-card-wrapper">
        <a href="/job_detail/ok_1.html"><span class="job-name">正常卡</span></a>
      </li>
    </ul>
    """
    cards = parse_boss_cards(html)
    assert len(cards) == 1
    assert cards[0]["title"] == "正常卡"


def test_parse_salary_with_bonus_months() -> None:
    result = parse_salary("25-50K·16薪")
    assert result == {"min_annual": 400000, "max_annual": 800000, "currency": "CNY"}


def test_parse_salary_default_twelve_months() -> None:
    result = parse_salary("15-25K")
    assert result["min_annual"] == 180000
    assert result["max_annual"] == 300000
    assert result["currency"] == "CNY"


def test_parse_salary_no_match_returns_empty() -> None:
    assert parse_salary("面议") == {}
    assert parse_salary("薪资面谈") == {}
    assert parse_salary("") == {}


def test_city_codes_and_build_search_url() -> None:
    assert CITY_CODES["深圳"] == "101280600"
    assert len(CITY_CODES) >= 10
    url = build_search_url("后端工程师", "深圳", page=2)
    assert url.startswith("https://www.zhipin.com/web/geek/job?")
    assert "query=" in url
    assert "city=101280600" in url
    assert "page=2" in url
    assert "page=1" in build_search_url("后端", "北京")


def test_build_search_url_accepts_raw_city_code() -> None:
    url = build_search_url("数据工程师", "101020100")
    assert "city=101020100" in url


def test_captcha_keyword_detection() -> None:
    assert detect_captcha_keywords("请完成安全验证后继续访问页面") == ["请完成安全验证"]
    assert detect_captcha_keywords("滑动验证失败，请重试") == ["滑动验证"]
    assert detect_captcha_keywords(_load_fixture()) == []
    assert detect_captcha_keywords("这里是正常职位列表页文本") == []
