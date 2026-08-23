"""决策报告端到端：抓取 → 归一化 → 存库 → 逐岗匹配 → 三元决策 → 报告 dict。

--offline-file 演示/测试模式可跳过浏览器（jobs 参数直接喂入）；
reflective_question 现阶段用规则模板生成（M3 换 LLM）。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from talentforge.decision.verdict import decide
from talentforge.domain.job import Job
from talentforge.domain.match import Match
from talentforge.domain.profile import Profile
from talentforge.field.risks import assess
from talentforge.llm.client import EnvLLMClient
from talentforge.matcher.coarse import CoarseMatcher
from talentforge.sources.boss_scraper import BossScraper
from talentforge.storage.db import DEFAULT_DB_PATH, init_db, upsert_job


def _risk_hits(field_notes: dict[str, object]) -> list[dict[str, str]]:
    hits = field_notes.get("hits")
    if not isinstance(hits, list):
        return []
    return [h for h in hits if isinstance(h, dict)]


def _reflective_question(
    job: Job, match: Match, field_notes: dict[str, object], profile: Profile
) -> str:
    """从风险命中 / 缺失维度 / 深层驱动里挑一句反思性反问（规则模板，M3 换 LLM）。"""
    hits = _risk_hits(field_notes)
    if hits:
        label = str(hits[0].get("label", ""))
        related = [db for db in profile.deal_breakers if db in match.structural.risks]
        if related:
            return f"这份岗位标着 {label}——你上次说{related[0]}是硬边界，现在怎么权衡？"
        return f"你怎么看这份工作的{label}？"
    if match.missing_dimensions:
        return f"岗位要求 {match.missing_dimensions[0]}，这是你想补的方向吗？"
    drive = profile.narrative.deep_drives[0] if profile.narrative.deep_drives else "长期方向"
    return f"这份工作推进你的{drive}吗？"


async def generate_report(
    profile: Profile,
    query: str,
    city: str,
    limit: int = 10,
    scraper: BossScraper | None = None,
    matcher: CoarseMatcher | None = None,
    conn: sqlite3.Connection | None = None,
    jobs: list[Job] | None = None,
) -> dict[str, Any]:
    """产出 Boss 岗位链路的决策报告 dict。

    默认构造 BossScraper / CoarseMatcher(EnvLLMClient()) / init_db(默认路径)；
    jobs 非 None 时跳过抓取器（offline-file 演示/测试）；conn/matcher 由调用方
    传入以便注入内存库与 FakeLLM。summary 统计 apply/hold/skip，items 每项含
    verdict、reason、risk_hits、reflective_question、gaps（LLM 无 gaps → []）。
    """
    if matcher is None:
        matcher = CoarseMatcher(EnvLLMClient())
    owns_conn = conn is None
    if conn is None:
        conn = init_db(DEFAULT_DB_PATH)

    if jobs is None:
        if scraper is None:
            scraper = BossScraper()
        async with scraper:
            jobs = await scraper.scrape(query, city, limit=limit, pages=3)
    else:
        jobs = jobs[:limit]

    counts = {"apply": 0, "hold": 0, "skip": 0}
    items: list[dict[str, object]] = []
    for job in jobs:
        upsert_job(conn, job)
        field_notes = assess(job)
        match = await matcher.match(profile, job, field_notes)
        verdict = decide(match, profile.deal_breakers)
        reason = match.reasoning[0] if match.reasoning else verdict.value
        items.append(
            {
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "url": job.url,
                "verdict": verdict.value,
                "reason": reason,
                "risk_hits": [str(hit.get("label", "")) for hit in _risk_hits(field_notes)],
                "gaps": match.gaps,
                "reflective_question": _reflective_question(job, match, field_notes, profile),
            }
        )
        counts[verdict.value] += 1

    if owns_conn:
        conn.close()

    return {
        "summary": {
            "n_jobs": len(jobs),
            "n_apply": counts["apply"],
            "n_hold": counts["hold"],
            "n_skip": counts["skip"],
        },
        "items": items,
    }
