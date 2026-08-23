"""探索路由（M7 spec §4）：POST /api/explore/snapshot、GET /api/explore/directions、
GET /api/explore/asset-brief。

snapshot：画像（缺失→空画像兜底，同 work.claims 风格）+ 全部作品 + 岗位库近
200 条 → generate_snapshot 一次 LLM 深推 → DirectionStore.replace_all（深谈
修正卡保留）→ 返回当前全部方向卡；生成失败返回 ok=False 契约不 500。
directions 直读方向库；asset-brief 纯数据盘点（画像缺失降级 {brief: None}）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from talentforge.api.common import load_profile
from talentforge.domain.profile import Profile
from talentforge.explore import store as explore_store
from talentforge.explore.engine import build_asset_brief, generate_snapshot
from talentforge.explore.store import DirectionStore
from talentforge.storage.db import list_jobs
from talentforge.work import store as work_store
from talentforge.work.store import WorkStore

router = APIRouter(tags=["explore"])


@router.post("/api/explore/snapshot")
async def post_explore_snapshot(request: Request) -> dict[str, Any]:
    """生成方向快照（3-5 张三口径方向卡）→ 存库 → 返回当前全部方向卡。"""
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = Profile(name="")
    artifacts = WorkStore(work_store.ARTIFACTS_PATH).list_all()
    jobs = list_jobs(request.app.state.conn, limit=200)
    cards, error = await generate_snapshot(profile, artifacts, jobs, request.app.state.llm)
    store = DirectionStore(explore_store.DIRECTIONS_PATH)
    store.replace_all(cards)
    return {
        "ok": not error,
        "generated": len(cards),
        "error": error,
        "directions": [c.model_dump(mode="json") for c in store.list_all()],
    }


@router.get("/api/explore/directions")
def get_explore_directions() -> dict[str, Any]:
    """已有方向卡列表。"""
    cards = DirectionStore(explore_store.DIRECTIONS_PATH).list_all()
    return {"directions": [c.model_dump(mode="json") for c in cards]}


@router.get("/api/explore/asset-brief")
def get_explore_asset_brief() -> dict[str, Any]:
    """资产盘点（纯数据无 LLM；深谈前置展示/纠错）；画像缺失降级不 404。"""
    try:
        profile = load_profile()
    except FileNotFoundError:
        return {"brief": None, "reason": "暂无画像"}
    artifacts = WorkStore(work_store.ARTIFACTS_PATH).list_all()
    return {"brief": build_asset_brief(profile, artifacts)}
