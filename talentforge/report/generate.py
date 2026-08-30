"""决策报告端到端：抓取 → 归一化 → 存库 → 并发匹配 → 三元决策 → 报告 dict。

--offline-file 演示/测试模式可跳过浏览器（jobs 参数直接喂入）；
reflective_question 现阶段用规则模板生成（M3 换 LLM）。
逐岗 LLM 匹配用信号量限并发（默认 5）——30 岗实测 146s 串行 → ~30s 并发；
items 顺序与 jobs 一致（gather 结果按序回收）。并发度现走
llm.settings.effective_match_concurrency（设置页 > env > 5，M8）。
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from typing import Any

from talentforge.decision.build import build_decision
from talentforge.domain.competency import CompetencyModel
from talentforge.domain.job import Job
from talentforge.domain.match import Match
from talentforge.domain.profile import Profile
from talentforge.field.risks import assess
from talentforge.llm.client import EnvLLMClient
from talentforge.llm.settings import effective_match_concurrency
from talentforge.matcher.coarse import CoarseMatcher
from talentforge.protocols import Matcher
from talentforge.sources.job_competency import CompetencyModelCache, RuleCompetencyClusterer
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
    matcher: Matcher | None = None,
    conn: sqlite3.Connection | None = None,
    jobs: list[Job] | None = None,
) -> dict[str, Any]:
    """产出岗位链路的决策报告 dict。

    采集走浏览器扩展（D25），本函数只消费库内岗位（jobs 必须传入，空 → 空报告）。
    默认构造 CoarseMatcher(EnvLLMClient()) / init_db(默认路径)；conn/matcher 由
    调用方传入以便注入内存库与 FakeLLM。summary 统计 apply/hold/skip，items
    每项含 verdict、reason、risk_hits、reflective_question、gaps、competency。
    """
    if matcher is None:
        matcher = CoarseMatcher(EnvLLMClient())
    owns_conn = conn is None
    if conn is None:
        conn = init_db(DEFAULT_DB_PATH)

    if jobs is None:
        jobs = []
    else:
        jobs = jobs[:limit]

    counts = {"apply": 0, "hold": 0, "skip": 0}
    for job in jobs:
        upsert_job(conn, job)

    # M9 岗位胜任力：先聚类分簇 → 每簇复用/新建模型 → 匹配时注入已知维度
    clusterer = RuleCompetencyClusterer()
    clusters = clusterer.cluster(jobs)
    cache = CompetencyModelCache()
    cached = cache.load()
    cluster_dimensions: dict[str, list[str]] = {}
    for cluster in clusters:
        model = cached.get(cluster.role_key)
        if model is not None:
            cluster_dimensions[cluster.role_key] = [d.name for d in model.dimensions]
    # 本批新模型：首个簇成员匹配结果中的 competency 维度固化（见 _decide_one）
    built_models: dict[str, CompetencyModel] = {}

    semaphore = asyncio.Semaphore(effective_match_concurrency())

    async def _decide_one(job: Job) -> dict[str, object]:
        field_notes = assess(job)
        role_key = clusterer.find_cluster(job) or _fallback_role_key(job)
        known = cluster_dimensions.get(role_key)
        async with semaphore:
            match = await matcher.match(profile, job, field_notes, known_dimensions=known)
        # 簇模型未建 → 用本岗对齐结果的维度名固化（同类岗位复用框架）
        if role_key not in built_models and match.competency:
            built_models[role_key] = CompetencyModel(
                role=job.title, role_key=role_key, level="",
                dimensions=[{"name": a.dimension} for a in match.competency],
                source=f"job:{job.id}",
            )
        # D15 核心：决策组装（象限+结构调制+M9 联动调制）收编 decision/build，
        # 报告 item 从 Decision 序列化（落库/导出共用同一事实源）
        decision = build_decision(
            job,
            match,
            risk_labels=[str(hit.get("label", "")) for hit in _risk_hits(field_notes)],
            profile=profile,
            reflective_question=_reflective_question(job, match, field_notes, profile),
        )
        return {
            "job_id": decision.job_id,
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "verdict": decision.verdict.value,
            "reason": decision.reason,
            "risk_hits": decision.risk_hits,
            "gaps": decision.gap,
            "competency": decision.competency,
            "reflective_question": decision.reflective_question,
        }

    items: list[dict[str, object]] = list(
        await asyncio.gather(*(_decide_one(job) for job in jobs))
    )
    for item in items:
        counts[str(item["verdict"])] += 1

    # 本批新建的簇模型写缓存（同类岗位后续复用）
    for model in built_models.values():
        cache.put(model)

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


def _fallback_role_key(job: Job) -> str:
    """cluster 未命中时的兜底 role_key（按 title 归一化，保证缓存可复用）。"""
    from talentforge.sources.job_competency import _title_key

    return _title_key(job.title) or f"job-{job.id}"
