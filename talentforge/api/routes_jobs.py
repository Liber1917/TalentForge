"""岗位工作台路由：GET /api/jobs + POST /api/jobs/batch（扩展采集入库，D25）。

storage.list_jobs → spec §1 工作台列表契约；verdict 取 decisions 缓存（对话/报告产出）
或缺省估算（deal-breaker→skip、有结构风险→hold、否则 apply，见 common.estimate_verdict）。
city 子串过滤 location、verdict 精确过滤、q 模糊匹配 title/company/location/salary；
空库返回 []（前端已有空态引导）。

POST /api/jobs/batch 是 D25 架构调整后的 Boss 岗位入库通道：浏览器扩展在
zhipin 搜索页内采集岗位卡（用户真实登录态），POST 到此处归一化落库——
服务器全程不碰 zhipin。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from talentforge.api.common import job_contract, load_profile
from talentforge.domain.job import Job
from talentforge.domain.profile import SalaryRange
from talentforge.sources.boss import parse_salary
from talentforge.sources.normalize import scan_risks
from talentforge.storage.db import list_jobs, upsert_job

router = APIRouter(tags=["jobs"])


class ExtensionJobCard(BaseModel):
    """扩展采集的岗位卡（extension/src/shared/platforms/boss.ts BossJobCard 契约）。"""

    title: str
    company: str = ""
    location: str = ""
    salary: str = ""
    url: str
    tags: list[str] = Field(default_factory=list)
    description: str = ""


class JobsBatchPayload(BaseModel):
    """POST /api/jobs/batch 请求体。"""

    source: str = "boss"
    jobs: list[ExtensionJobCard] = Field(default_factory=list)


def _to_job(card: ExtensionJobCard, source: str) -> Job:
    """扩展岗位卡 → Job（薪资/风险标记复用 M2a 解析器）。"""
    salary_raw = parse_salary(card.salary)
    salary = (
        SalaryRange(
            min_annual=int(salary_raw["min_annual"]),
            max_annual=int(salary_raw["max_annual"]),
            currency=str(salary_raw.get("currency", "CNY")),
        )
        if salary_raw
        else None
    )
    haystack = f"{card.title} {card.company} {card.description} {' '.join(card.tags)}"
    return Job(
        source=source,
        title=card.title,
        company=card.company,
        location=card.location,
        url=card.url,
        description=card.description,
        salary=salary,
        tags=card.tags,
        risk_keys=scan_risks(haystack),
    )


@router.post("/api/jobs/batch")
def receive_jobs_batch(payload: JobsBatchPayload, request: Request) -> dict:
    """扩展采集岗位批量入库（按 url 去重）；返回新增数与总数。"""
    conn = request.app.state.conn
    inserted = 0
    for card in payload.jobs:
        if upsert_job(conn, _to_job(card, payload.source)):
            inserted += 1
    return {"ok": True, "received": len(payload.jobs), "inserted": inserted}


@router.get("/api/jobs")
def get_jobs(request: Request, city: str = "", verdict: str = "", q: str = "") -> list[dict]:
    """工作台岗位列表：映射为工作台契约并应用 city/verdict/q 过滤。"""
    state = request.app.state
    jobs = list_jobs(state.conn, limit=200)
    try:
        deal_breakers = load_profile().deal_breakers
    except FileNotFoundError:
        deal_breakers = []
    items = [job_contract(job, state.decisions, deal_breakers) for job in jobs]

    if city:
        items = [item for item in items if city in item["location"]]
    if verdict:
        items = [item for item in items if item["verdict"] == verdict]
    if q:
        needle = q.lower()
        items = [
            item
            for item in items
            if needle
            in " ".join([item["title"], item["company"], item["location"], item["salary"]]).lower()
        ]
    return items
