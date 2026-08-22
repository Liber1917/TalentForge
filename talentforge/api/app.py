"""FastAPI 应用工厂：健康检查 + 事件接收（复用 handle_events）+ 静态挂载 + 宽松 CORS。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from talentforge.api.events import handle_events
from talentforge.api.routes_chat import router as chat_router
from talentforge.api.routes_claims import router as claims_router
from talentforge.api.routes_jobs import router as jobs_router
from talentforge.api.routes_profile import router as profile_router
from talentforge.api.routes_report import router as report_router
from talentforge.api.routes_sources import router as sources_router
from talentforge.llm.client import EnvLLMClient, LLMClient
from talentforge.storage.db import DEFAULT_DB_PATH, init_db

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_WEB_DIR = _PACKAGE_ROOT / "web"


def _default_conn() -> sqlite3.Connection:
    """应用级默认连接（server 生命周期内持有，多线程共享）。"""
    return init_db(DEFAULT_DB_PATH, check_same_thread=False)


def create_app(
    conn: sqlite3.Connection | None = None,
    web_dir: str | Path | None = None,
    llm: LLMClient | None = None,
) -> FastAPI:
    """构造 TalentForge FastAPI 应用。

    - GET /api/health → {"ok": true}
    - POST /api/events → 复用 handle_events 纯函数（幂等契约不变），ok=False 时返回 400
    - M3 真端点：/api/chat /api/claims /api/jobs /api/report /api/profile（路由内用 /api 绝对路径）
    - 静态挂载 web/ → /（无 index.html 时 404，保持挂载在最后）
    - CORS 宽松（本地工具）

    conn 默认 init_db(DEFAULT_DB_PATH, check_same_thread=False)；web_dir 默认仓库根下 web/；
    llm 默认 EnvLLMClient()（测试可注入 FakeLLM）。应用级可变状态（对话历史/报告任务/
    决策缓存）挂在 app.state，随 app 实例隔离。
    """
    if conn is None:
        conn = _default_conn()
    if web_dir is None:
        web_dir = DEFAULT_WEB_DIR

    app = FastAPI(title="TalentForge", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.conn = conn
    app.state.llm = llm if llm is not None else EnvLLMClient()
    app.state.chat_turns = []
    app.state.report_tasks = {}
    app.state.decisions = {}

    @app.get("/api/health")
    def health() -> dict:
        """健康检查端点。"""
        return {"ok": True}

    @app.post("/api/events")
    def receive_events(payload: dict, _request: Request) -> JSONResponse:
        """接收插件采集事件：逐条校验入库，ok=False 时返回 400。"""
        result = handle_events(payload, conn)
        return JSONResponse(status_code=200 if result["ok"] else 400, content=result)

    app.include_router(chat_router)
    app.include_router(claims_router)
    app.include_router(jobs_router)
    app.include_router(report_router)
    app.include_router(profile_router)
    app.include_router(sources_router)

    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app
