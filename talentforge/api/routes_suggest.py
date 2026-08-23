"""推荐路由（M6 spec §2.2）：POST /api/suggest、POST /api/suggest/for-job。

suggest：gap 技能 → 推荐 repo 列表（走 24h 缓存，见 project_suggest）。
for-job：读 decisions 缓存（job_url → gaps，matcher 产出）逐 gap 推荐；
gaps 不在 jobs 表而在 app.state.decisions 内存缓存；单 gap 推荐失败
（WorkSourceError）→ 该项 suggestions 空但记 warning，不阻断其他 gap。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from talentforge.api.common import load_profile
from talentforge.sources.project_suggest import suggest_projects
from talentforge.sources.work_sources import WorkSourceError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["suggest"])


class SuggestRequest(BaseModel):
    """POST /api/suggest body：gap 技能名 + 可选语言限定。"""

    gap_skill: str
    language: str = ""


class SuggestForJobRequest(BaseModel):
    """POST /api/suggest/for-job body：目标岗位 url（decisions 缓存键）。"""

    job_url: str


def _profile_language() -> str:
    """画像主语言（skills[0]，可选富化）；画像缺失/为空 → 空串不加限定。"""
    try:
        skills = load_profile().skills
    except (FileNotFoundError, ValueError):
        return ""
    return str(skills[0]) if skills else ""


@router.post("/api/suggest")
async def suggest(body: SuggestRequest) -> dict:
    """gap 技能 → 推荐 repo（缓存优先；限流/网络失败上抛 500 由前端提示）。"""
    suggestions = await suggest_projects(body.gap_skill, language=body.language)
    return {"ok": True, "gap_skill": body.gap_skill, "suggestions": suggestions}


@router.post("/api/suggest/for-job")
async def suggest_for_job(body: SuggestForJobRequest, request: Request) -> dict:
    """job 的 gaps → 逐 gap 推荐列表。

    gaps 读 app.state.decisions[job_url]（报告任务写入的内存缓存）；
    无缓存/无 gaps → {ok, gaps: []}；单 gap 推荐失败（WorkSourceError）
    → 该项 suggestions 空并记 warning，不阻断其余 gap。
    """
    decisions: dict[str, dict[str, Any]] = request.app.state.decisions
    entry = decisions.get(body.job_url)
    gaps = entry.get("gaps") if isinstance(entry, dict) else None
    if not isinstance(gaps, list):
        gaps = []
    if not gaps:
        return {"ok": True, "gaps": []}

    language = _profile_language()
    results: list[dict[str, Any]] = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        skill = str(gap.get("skill") or "").strip()
        if not skill:
            continue
        item: dict[str, Any] = {
            "skill": skill,
            "severity": str(gap.get("severity") or ""),
            "suggestions": [],
        }
        try:
            item["suggestions"] = await suggest_projects(skill, language=language)
        except WorkSourceError as exc:
            item["warning"] = str(exc)
            logger.warning("gap %s 推荐失败: %s", skill, exc)
        results.append(item)
    return {"ok": True, "results": results}
