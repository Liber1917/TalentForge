"""岗位归一化：Boss 卡片 dict → 领域 Job，附场域风险关键词扫描。"""

from __future__ import annotations

from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange
from talentforge.sources.boss import parse_salary

# 结构性风险扫描关键词（精确子串匹配）——与 talentforge/field/risks.py 的键对齐
RISK_KEYWORDS: list[str] = [
    "996", "大小周", "单休", "无偿加班", "竞业限制", "加班费", "无社保", "弹性工作制",
]

# 扫描命中 → 场域风险库 canonical key 的归一映射（"加班费"是"加班费模糊"的子串）
RISK_KEY_ALIASES: dict[str, str] = {"加班费": "加班费模糊"}


def scan_risks(text: str) -> list[str]:
    """扫描文本中的结构性风险关键词，返回 field/risks.py 的 canonical key 列表（去重保序）。"""
    hits = [keyword for keyword in RISK_KEYWORDS if keyword in text]
    return [RISK_KEY_ALIASES.get(keyword, keyword) for keyword in hits]


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
