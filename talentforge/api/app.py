"""FastAPI 应用工厂：健康检查 + 事件接收（复用 handle_events）+ 静态挂载 + Origin 校验。

Origin 校验（M10 安全批次）：本地服务默认只服务本机，拒绝跨站请求（恶意网页
对 127.0.0.1:8420 的 CSRF）。同源/无 Origin 头（curl/扩展）/localhost Origin 放行。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from talentforge.api.common import load_profile
from talentforge.api.events import handle_events
from talentforge.api.routes_chat import router as chat_router
from talentforge.api.routes_claims import router as claims_router
from talentforge.api.routes_explore import router as explore_router
from talentforge.api.routes_feedback import router as feedback_router
from talentforge.api.routes_jobs import router as jobs_router
from talentforge.api.routes_llm import router as llm_router
from talentforge.api.routes_onboarding import router as onboarding_router
from talentforge.api.routes_profile import router as profile_router
from talentforge.api.routes_report import router as report_router
from talentforge.api.routes_resume import router as resume_router
from talentforge.api.routes_sources import router as sources_router
from talentforge.api.routes_suggest import router as suggest_router
from talentforge.api.routes_tasks import router as tasks_router
from talentforge.api.routes_work import router as work_router
from talentforge.llm.client import EnvLLMClient, LLMClient
from talentforge.storage.db import DEFAULT_DB_PATH, init_db

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_WEB_DIR = _PACKAGE_ROOT / "web"
# Host 白名单 = DNS rebinding 防线：同源 fetch 可省略 Origin 头，但浏览器无法伪造 Host。
# testserver 是 Starlette TestClient 的约定 Host，仅测试流量使用。
_ALLOWED_HOSTNAMES = ("127.0.0.1", "localhost", "::1", "testserver")


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
    - M4 反馈端点：/api/feedback（events POST/GET + summary，驱动偏好回流管线）
    - M5 作品端点：/api/work（fetch/artifacts/claims/dismiss，作品源→画像主张）
    - M6 推荐端点：/api/suggest（gap→GitHub 优质 repo，24h 缓存）/api/suggest/for-job
    - M7 探索端点：/api/explore（snapshot/directions/asset-brief，三口径方向卡快照）
    - M5 简历产出：GET /cv（Jinja2 A4 模板渲染，旧 /resume 302 跳转，路由先于静态挂载）
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

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Host + Origin 双校验：拒绝跨站请求与 DNS rebinding。

        Host 校验：恶意页把域名重绑到 127.0.0.1 后浏览器视为同源 fetch（不带
        Origin 头），但 Host 仍是 rebinder 域——非本机 Host 一律 403。
        Origin 校验（M10）：恶意网页对 127.0.0.1:8420 发请求时 Origin 是攻击
        站点，必须拒绝；无 Origin 头（curl/扩展 fetch/同源导航）放行。
        例外：POST /api/events 放行三个采集平台域（扩展 content script 在
        zhipin/bilibili/zhihu 页面内上报，Origin 是站点域）——该端点只做
        校验式入库（事件进 trial 主张链，有用户确认闸门），无敏感读。
        """
        host_header = (request.headers.get("host") or "").strip()
        hostname = urlparse(f"//{host_header}").hostname or "" if host_header else ""
        if hostname not in _ALLOWED_HOSTNAMES:
            return JSONResponse(status_code=403, content={"detail": "forbidden host"})
        origin = request.headers.get("origin")
        if origin:
            parsed_origin = urlparse(origin)
            host = parsed_origin.hostname or ""
            if host not in ("127.0.0.1", "localhost"):
                # M11：扩展 service-worker 的 fetch 带 chrome-extension:// Origin
                #（Chromium 151 实测）——本机扩展与本机 curl 同信任域，仅对
                # 采集摄入端点放行（events/jobs/tasks）；其余端点仍拒扩展来源。
                extension_ingest = parsed_origin.scheme == "chrome-extension" and (
                    request.url.path in ("/api/events", "/api/jobs/batch")
                    or request.url.path.startswith("/api/tasks")
                )
                if not extension_ingest and not (
                    request.url.path == "/api/events"
                    and request.method == "POST"
                    and (
                        host.endswith(".zhipin.com")
                        or host.endswith(".bilibili.com")
                        or host.endswith(".zhihu.com")
                    )
                ):
                    return JSONResponse(status_code=403, content={"detail": "forbidden origin"})
        return await call_next(request)

    app.state.conn = conn
    app.state.llm = llm if llm is not None else EnvLLMClient()
    app.state.chat_turns = []
    app.state.report_tasks = {}
    app.state.decisions = {}
    # 画像快照（M10 回测地基）：决策落库时附带，供回测还原当时画像状态
    try:
        app.state.profile_snapshot = load_profile().model_dump(mode="json")
    except (OSError, ValueError) as exc:  # 文件缺失/损坏不阻断启动；编程错误照常炸
        logger.warning("画像快照加载失败（决策落库将无快照）: %s", exc)
        app.state.profile_snapshot = None

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
    app.include_router(feedback_router)
    app.include_router(sources_router)
    app.include_router(llm_router)
    app.include_router(onboarding_router)
    app.include_router(suggest_router)
    app.include_router(tasks_router)
    app.include_router(work_router)
    app.include_router(explore_router)
    app.include_router(resume_router)

    # 本地工具：静态资源禁缓存（JS/CSS 迭代频繁，旧缓存是"改了不生效"的头号来源）
    app.mount(
        "/",
        NoCacheStaticFiles(directory=str(web_dir), html=True),
        name="web",
    )
    return app


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles + Cache-Control: no-store（仅本地开发服务用）。"""

    def file_response(self, *args: object, **kwargs: object) -> object:  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)  # type: ignore[no-untyped-call]
        resp.headers["Cache-Control"] = "no-store"
        return resp
