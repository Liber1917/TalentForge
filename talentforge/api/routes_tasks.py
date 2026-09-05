"""M11 采集任务路由：visit 入队（policy 闸门）/ next 领取 / report 回报。

D30 分级采集的 auto 通道服务端：enqueue 仅对 auto 平台放行（manual/assist/blocked
一律 403 并说明模式）；风控冷却期内 403；日配额用尽 429。dwell_ms 由服务端封顶
（db 层 30s 硬顶），客户端不传则随机 8-25s 拟人抖动。
"""

from __future__ import annotations

import json
import random
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from talentforge.sources.collection_policy import (
    COOLDOWN_MINUTES,
    MODE_AUTO,
    daily_quota,
    load_policy,
    mode_for,
)
from talentforge.storage.db import (
    claim_next_task,
    count_tasks_today,
    enqueue_task,
    list_tasks,
    platform_in_cooldown,
    report_task,
)

router = APIRouter(tags=["tasks"])


class VisitPayload(BaseModel):
    """POST /api/tasks/visit 请求体。"""

    platform: str
    urls: list[str] = Field(default_factory=list)
    dwell_ms: int | None = None


class ReportPayload(BaseModel):
    """POST /api/tasks/{id}/report 请求体（非法 status 由 pydantic 拒 422）。"""

    status: Literal["done", "failed", "aborted"]
    inserted: int | None = None
    risk_signal: str | None = None
    error: str | None = None


@router.post("/api/tasks/visit")
def enqueue_visits(payload: VisitPayload, request: Request) -> dict:
    """批量入队访问任务：policy 非 auto → 403；冷却中 → 403；配额尽 → 429。"""
    conn = request.app.state.conn
    policy = load_policy()
    mode = mode_for(payload.platform, policy)
    if mode != MODE_AUTO:
        raise HTTPException(
            status_code=403,
            detail=f"平台 {payload.platform} 采集模式为 {mode}，仅 auto 平台可入队",
        )
    if platform_in_cooldown(conn, payload.platform, COOLDOWN_MINUTES):
        raise HTTPException(
            status_code=403,
            detail=f"平台 {payload.platform} 风控冷却中（{COOLDOWN_MINUTES}min）",
        )

    quota = daily_quota(payload.platform, policy)
    remaining = quota - count_tasks_today(conn, payload.platform)
    task_ids: list[int] = []
    rejected: list[dict[str, str]] = []
    for url in payload.urls:
        if remaining <= 0:
            rejected.append({"url": url, "reason": "daily_quota"})
            continue
        dwell = payload.dwell_ms if payload.dwell_ms is not None else random.randint(8_000, 25_000)
        tid = enqueue_task(conn, payload.platform, url, dwell_ms=dwell)
        if tid is None:
            rejected.append({"url": url, "reason": "duplicate_active"})
            continue
        task_ids.append(tid)
        remaining -= 1

    if not task_ids and rejected:
        reason = rejected[0]["reason"]
        if reason == "daily_quota":
            raise HTTPException(
                status_code=429,
                detail=f"平台 {payload.platform} 当日配额（{quota}）已用尽",
            )
        raise HTTPException(status_code=409, detail="任务已存在（重复入队）")
    return {"ok": True, "enqueued": len(task_ids), "task_ids": task_ids, "rejected": rejected}


@router.get("/api/tasks/next")
def next_task(runner: str, request: Request) -> Response:
    """runner 原子领取最早 pending 任务；无任务 204。"""
    task = claim_next_task(request.app.state.conn, runner)
    if task is None:
        return Response(status_code=204)
    return Response(content=json.dumps(task, ensure_ascii=False), media_type="application/json")


@router.post("/api/tasks/{task_id}/report")
def report(task_id: int, payload: ReportPayload, request: Request) -> dict:
    """runner 回报终态；任务不存在或非 running → 404。"""
    ok = report_task(
        request.app.state.conn,
        task_id,
        status=payload.status,
        inserted=payload.inserted,
        risk_signal=payload.risk_signal,
        error=payload.error,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已完结")
    return {"ok": True}


@router.get("/api/tasks")
def get_tasks(request: Request, limit: int = 50) -> dict:
    """最近采集任务（设置页风控事件展示 / 验收可见性）。"""
    tasks: list[dict[str, Any]] = list_tasks(request.app.state.conn, limit=limit)
    return {"tasks": tasks}
