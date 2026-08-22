"""岗位工作台路由：GET /api/jobs。

storage.list_jobs → spec §1 工作台列表契约；verdict 取 decisions 缓存（对话/报告产出）
或缺省估算（deal-breaker→skip、有结构风险→hold、否则 apply，见 common.estimate_verdict）。
city 子串过滤 location、verdict 精确过滤、q 模糊匹配 title/company/location/salary；
空库返回 []（前端已有空态引导）。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from talentforge.api.common import job_contract, load_profile
from talentforge.storage.db import list_jobs

router = APIRouter(tags=["jobs"])


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
