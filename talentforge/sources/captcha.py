"""验证码 / 安全拦截关键词检测（HTML 文本层；选择器级检测在 Playwright 层做）。"""

from __future__ import annotations

CAPTCHA_KEYWORDS: list[str] = [
    "请完成安全验证",
    "滑动验证",
    "图形验证",
    "安全检测",
]


def detect_captcha_keywords(text: str) -> list[str]:
    """检测文本命中的验证码关键词清单（空列表表示未命中）。"""
    return [keyword for keyword in CAPTCHA_KEYWORDS if keyword in text]


def detect_captcha(html_text: str) -> list[str]:
    """detect_captcha_keywords 的计划接口别名（Task 2 抓取循环使用）。"""
    return detect_captcha_keywords(html_text)
