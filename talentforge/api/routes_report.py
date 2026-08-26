"""异步报告路由：POST /api/report/run → 后台跑 generate_report → GET /api/report/status 轮询。

状态存内存 dict（task_id → state: running/done/failed + result/error）；
POST 返回 {task_id, state:running}，GET /api/report/status 不带 task_id 时返回最新任务。
任务复用 app.state.conn / app.state.llm；jobs 从库读（采集走浏览器扩展，空库返回空报告）。
产物写 decisions 缓存（job_url → verdict/reason/gaps），供 GET /api/jobs 显示。
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel

from talentforge.api.common import load_profile
from talentforge.matcher.coarse import CoarseMatcher
from talentforge.report.generate import generate_report
from talentforge.storage.db import list_jobs

router = APIRouter(tags=["report"])


class ReportPayload(BaseModel):
    """POST /api/report/run 请求体。"""

    query: str = "后端"
    city: str = ""
    limit: int = 20


def _store_decisions(state: Any, items: list[dict[str, object]]) -> None:
    """把 report items 的 verdict/reason/gaps/competency 落库 + 内存缓存。

    内存缓存（state.decisions，job_url 键控）供 GET /api/jobs 工作台实时显示；
    decisions 表 append-only 落库（M10 回测地基）——服务重启不丢，可导出回测。
    """
    for item in items:
        url = str(item.get("url"))
        if not url:
            continue
        record = {
            "verdict": str(item.get("verdict")),
            "reason": str(item.get("reason", "")),
            "gaps": item.get("gaps", []),
        }
        state.decisions[url] = record
        try:
            from talentforge.storage.db import insert_decision

            insert_decision(
                state.conn,
                job_url=url,
                source=str(item.get("source", "boss")),
                title=str(item.get("title", "")),
                company=str(item.get("company", "")),
                verdict=record["verdict"],
                reason=record["reason"],
                gaps=record["gaps"],
                competency=item.get("competency", []),
                profile_snapshot=getattr(state, "profile_snapshot", None),
            )
        except Exception as exc:  # noqa: BLE001 — 决策落库失败不影响主流程
            import logging

            logging.getLogger(__name__).warning("决策落库失败: %s", exc)


@router.post("/api/report/run")
async def run_report(payload: ReportPayload, request: Request) -> dict:
    """起后台任务跑报告管线，立即返回 task_id（前端轮询 status）。"""
    state = request.app.state
    task_id = uuid4().hex
    entry: dict[str, Any] = {"state": "running", "task": None}
    state.report_tasks[task_id] = entry
    task = asyncio.create_task(_run_report_task(request.app, task_id, payload))
    entry["task"] = task
    return {"task_id": task_id, "state": "running"}


@router.get("/api/report/status")
def report_status(request: Request, task_id: str | None = None) -> dict:
    """查询报告任务状态；未指定 task_id 时返回最近一次任务。"""
    tasks: dict[str, dict[str, Any]] = request.app.state.report_tasks
    if not tasks:
        return {"state": "idle"}
    key = task_id if task_id is not None else next(reversed(tasks))
    entry = tasks[key]
    result: dict[str, Any] = {"state": entry["state"]}
    if entry.get("result") is not None:
        result.update(entry["result"])
    if entry.get("error"):
        result["error"] = entry["error"]
    return result


async def _run_report_task(app: Any, task_id: str, payload: ReportPayload) -> None:
    """后台任务：读库 jobs → generate_report → 更新任务状态（采集走扩展，空库返回空报告）。"""
    state = app.state
    entry = state.report_tasks[task_id]
    try:
        conn = state.conn
        jobs = list_jobs(conn, limit=payload.limit)
        profile = load_profile()
        matcher = CoarseMatcher(state.llm)
        report = await generate_report(
            profile,
            payload.query,
            payload.city,
            limit=payload.limit,
            matcher=matcher,
            conn=conn,
            jobs=jobs or None,
        )
        _store_decisions(state, report.get("items") or [])
        entry["result"] = report
        entry["state"] = "done"
    except Exception as exc:
        entry["error"] = str(exc)
        entry["state"] = "failed"
