"""首启引导状态端点（M10 分发）：GET /api/onboarding/status。

一次调用返回新用户进度（image/extension/llm/decisions 四维布尔），
对话页空态据此渲染三步引导卡——小白 exe 首启不迷茫。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["onboarding"])


@router.get("/api/onboarding/status")
def onboarding_status(request: Request) -> dict:
    """四维就绪状态：profile/extension/llm/decisions。

    - profile: 画像是否已有叙事主张（narrative_claims 非空）
    - extension: 是否有扩展采集的岗位/事件入库（jobs/events 非空）
    - llm: LLM 配置是否就绪（设置文件或 env 或回退链可用）
    - decisions: 是否跑过决策（decisions 表非空）
    """
    state = request.app.state
    conn = state.conn

    profile_ok = False
    try:
        from talentforge.api.common import load_profile

        p = load_profile()
        profile_ok = bool(p.name or p.narrative_claims or p.skills)
    except Exception:  # noqa: BLE001 — 画像缺失按未就绪
        profile_ok = False

    extension_ok = False
    try:
        jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        extension_ok = (jobs or 0) > 0 or (events or 0) > 0
    except Exception:  # noqa: BLE001 — 表缺失按未就绪
        extension_ok = False

    llm_ok = False
    try:
        from talentforge.llm.settings import effective_settings

        _settings, _source = effective_settings()
        llm_ok = bool(_settings.base_url and _settings.model)
    except Exception:  # noqa: BLE001 — 配置缺失按未就绪
        llm_ok = False

    decisions_ok = False
    try:
        n = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        decisions_ok = (n or 0) > 0
    except Exception:  # noqa: BLE001 — 表缺失按未就绪
        decisions_ok = False

    return {
        "ok": True,
        "profile": profile_ok,
        "extension": extension_ok,
        "llm": llm_ok,
        "decisions": decisions_ok,
    }
