"""反馈路由（spec §2）：POST/GET /api/feedback/events、GET /api/feedback/summary。

POST 单端点驱动整条回流管线：store.append（幂等）→ 反查 Job（url == job_id，
Job 主键是 url；找不到按 job=None 只做叙事修正）→ FeedbackPipeline.apply →
profile 写回（即使无变更也写回，保持简单）。画像路径复用 api/common
（TALENTFORGE_PROFILE_PATH 覆盖；文件缺失时空画像兜底，不 500）。
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from talentforge.api.common import load_profile, save_profile
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.job import Job
from talentforge.domain.profile import Profile
from talentforge.feedback import store as feedback_store
from talentforge.feedback.engine import FeedbackPipeline
from talentforge.feedback.store import FeedbackStore
from talentforge.storage.db import list_jobs

router = APIRouter(tags=["feedback"])


def _find_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    """按 url（Job 主键）在最近 200 条岗位里反查；未命中返回 None。"""
    for job in list_jobs(conn, limit=200):
        if job.url == job_id:
            return job
    return None


@router.post("/api/feedback/events")
def post_feedback_event(event: FeedbackEvent, request: Request) -> dict:
    """记录决策/结果并驱动回流管线（偏好段位 evidence/升位 + 叙事修正）。

    幂等由 store.append 保证（同 job_id+action 更新不重复）；返回变更摘要列表
    （changes 为空表示本次事件未触发任何偏好/叙事调整）。
    """
    store = FeedbackStore(feedback_store.FEEDBACK_LOG_PATH)
    store.append(event)
    job = _find_job(request.app.state.conn, event.job_id)
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = Profile(name="")
    new_profile, changes = FeedbackPipeline().apply(profile, event, job)
    save_profile(new_profile)
    return {
        "ok": True,
        "event": event.model_dump(mode="json"),
        "preference_changes": changes,
    }


@router.get("/api/feedback/events")
def get_feedback_events(limit: int = 50) -> dict:
    """最近回流条目（按 at 倒序，limit 截断；负数按 0 处理）。"""
    store = FeedbackStore(feedback_store.FEEDBACK_LOG_PATH)
    events = store.recent(max(limit, 0))
    return {"events": [e.model_dump(mode="json") for e in events]}


@router.get("/api/feedback/summary")
def get_feedback_summary() -> dict:
    """回流统计（n_decided 与 apply/hold/skip 分布 + n_outcome）。

    deviation：spec §2 列出的"偏好调整次数"无独立数据源（偏好变更只落
    profile.utility_preferences 的 ordering/evidence，未单独计数）——不虚构该值；
    需要时可从 profile 各 OrdinalPreference.evidence 条目数近似，暂不实现。
    """
    store = FeedbackStore(feedback_store.FEEDBACK_LOG_PATH)
    return {"summary": store.summary()}
