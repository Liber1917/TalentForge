"""岗位归一化：Boss 卡片 dict → 领域 Job，附场域风险关键词扫描。"""

from __future__ import annotations

from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange
from talentforge.sources.boss import parse_salary

# 结构性风险关键词（精确子串匹配；"加班费"出现说明有加班费讨论，中性但值得标记）
RISK_KEYWORDS: list[str] = ["996", "大小周", "单休", "无偿加班", "竞业限制", "加班费"]


def scan_risks(text: str) -> list[str]:
    """扫描文本中的结构性风险关键词，返回命中列表（按清单顺序去重）。"""
    return [keyword for keyword in RISK_KEYWORDS if keyword in text]


def normalize_to_job(card: dict[str, object], city: str) -> Job:
    """将 parse_boss_cards 的卡片 dict 组装为归一化 Job。

    location 用搜索城市；description 为原文 + tags 拼接的全文；
    薪资文本经 parse_salary 归一为年薪 SalaryRange（解析失败为 None）；
    risk_keys 对 description + tags 全文做风险扫描。
    """
    tags = [str(tag) for tag in card.get("tags") or []]
    description = str(card.get("description") or "")
    full_text = " ".join(part for part in [description, *tags] if part)
    salary_raw = parse_salary(str(card.get("salary_text") or ""))
    salary = SalaryRange(**salary_raw) if salary_raw else None
    return Job(
        source="boss",
        title=str(card.get("title") or ""),
        company=str(card.get("company") or ""),
        location=city,
        url=str(card.get("href") or ""),
        description=full_text,
        salary=salary,
        tags=tags,
        risk_keys=scan_risks(full_text),
    )
