"""平台源路由：GET /api/sources（源卡状态）、POST /api/sources/boss/credential（页面保存）、
POST /api/sources/boss/verify（轻量连通性验证，真实外呼）。

设计参考 OpenBiliClaw 平台源页：
- 每个来源一张卡（名称 + 接入状态徽章 + 脱敏摘要），展开可粘贴凭据；
- 凭据只进不出——后端永不回传原始 cookie，仅返回前4后4掩码摘要；
- 留空保存不覆盖现有值（空串语义，OpenBiliClaw）；
- 接入方式分级：cookie 源给粘贴入口，插件源标注无需配置，公开源标注公开接口。

verify 为启发式判定（详见 _judge_verify），网络失败优雅降级返回 ok=False，绝不 500。
"""

from __future__ import annotations

import logging

import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from talentforge.sources.cookies import (
    get_boss_cookie_summary,
    resolve_boss_raw,
    save_boss_cookie,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sources"])

# verify 外呼参数（测试经 _VERIFY_TRANSPORT 注入 httpx.MockTransport 伪造响应，不打真实网络）
_VERIFY_TRANSPORT: httpx.AsyncBaseTransport | None = None
_VERIFY_TIMEOUT: float = 10.0
_VERIFY_URL = "https://www.zhipin.com/"
_VERIFY_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# set-cookie 中的登录态清除痕迹：空值（foo=;）或_epoch 过期（Expires=Thu, 01 Jan 1970）
_SET_COOKIE_CLEARED_RE = re.compile(r"=\s*;|Expires=Thu, 01 Jan 1970")

_SOURCE_NOTES = {
    "boss": "由浏览器插件在你的真实登录态内采集（D25）：装插件后在 Boss 搜索页浏览即自动入库，无需配置 cookie",
    "bilibili": "由浏览器插件登录态采集，无需配置 cookie",
    "zhihu": "由浏览器插件登录态采集，无需配置 cookie",
    "github": "公开 API 可用；展开输入用户名即可拉取仓库作品（未认证 60 次/时，env TALENTFORGE_GITHUB_TOKEN 可提额）",
    "gitee": "公开 API 可用；展开输入 Gitee 用户名即可拉取公开仓库作品",
    "arxiv": "输入作者名（如 Zhang San）拉取论文；preprint 信号上限 normal，标题含顶会名查 CCF 升 strong",
}


@router.get("/api/sources")
def list_sources() -> dict:
    """平台源卡片状态列表：boss 状态实时解析，其余为静态接入说明。"""
    return {
        "sources": [
            {
                "key": "boss",
                "name": "Boss 直聘",
                "kind": "extension",
                "home": "https://www.zhipin.com/",
                "nav": "self",
                "status": {"source": "extension", "masked": ""},
                "note": _SOURCE_NOTES["boss"],
            },
            {
                "key": "bilibili",
                "name": "B站",
                "kind": "extension",
                "home": "https://www.bilibili.com/",
                "nav": "blank",
                "status": {"source": "extension", "masked": ""},
                "note": _SOURCE_NOTES["bilibili"],
            },
            {
                "key": "zhihu",
                "name": "知乎",
                "kind": "extension",
                "home": "https://www.zhihu.com/",
                "nav": "blank",
                "status": {"source": "extension", "masked": ""},
                "note": _SOURCE_NOTES["zhihu"],
            },
            {
                "key": "github",
                "name": "GitHub",
                "kind": "public",
                "home": "https://github.com/",
                "nav": "blank",
                "status": {"source": "public", "masked": ""},
                "note": _SOURCE_NOTES["github"],
            },
            {
                "key": "gitee",
                "name": "Gitee",
                "kind": "public",
                "home": "https://gitee.com/",
                "nav": "blank",
                "status": {"source": "public", "masked": ""},
                "note": _SOURCE_NOTES["gitee"],
            },
            {
                "key": "arxiv",
                "name": "arXiv",
                "kind": "public",
                "home": "https://arxiv.org/",
                "nav": "blank",
                "status": {"source": "public", "masked": ""},
                "note": _SOURCE_NOTES["arxiv"],
            },
        ]
    }


@router.post("/api/sources/boss/credential")
def save_boss_credential(body: dict) -> dict:
    """页面保存 Boss cookie；空串 = 不覆盖（OpenBiliClaw 语义），返回当前摘要。"""
    if not isinstance(body, dict) or not isinstance(body.get("cookie"), str):
        raise HTTPException(status_code=400, detail="需要 cookie 字符串字段（留空表示不覆盖）")
    raw = body["cookie"]
    if raw.strip():
        try:
            save_boss_cookie(raw)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"凭据文件写入失败：{exc}") from exc
    return {"ok": True, "status": get_boss_cookie_summary()}


def _judge_verify(resp: httpx.Response) -> dict:
    """启发式判定登录态是否有效（简单规则，非精确）：

    - 301/302/303/307/308：zhipin 未登录态访问首页常见跳登录 → invalid；
    - 401/403：风控/拒绝 → invalid；
    - 200：set-cookie 出现清除痕迹（空值或 1970 过期）→ invalid，否则 ok；
    - 其余状态码：无法判断，ok=False 附 HTTP 状态。
    """
    status = resp.status_code
    if status in (301, 302, 303, 307, 308):
        return {"ok": False, "detail": f"cookie 已失效（HTTP {status} 跳转登录）"}
    if status in (401, 403):
        return {"ok": False, "detail": f"cookie 已失效（HTTP {status} 被拒绝）"}
    if status == 200:
        set_cookies = "; ".join(resp.headers.get_list("set-cookie"))
        if _SET_COOKIE_CLEARED_RE.search(set_cookies):
            return {"ok": False, "detail": "cookie 已失效（响应含清除登录态痕迹）"}
        return {"ok": True, "detail": "连接正常"}
    return {"ok": False, "detail": f"无法判断（HTTP {status}），建议稍后重试"}


@router.post("/api/sources/boss/verify")
async def verify_boss() -> dict:
    """用当前解析链的 cookie 做轻量验证：GET zhipin 首页（带 cookie + 浏览器 UA）。

    网络错误/超时返回 {ok: false, detail: "网络错误：…"}，不 500。
    """
    _source, raw = resolve_boss_raw()
    if not raw:
        return {"ok": False, "detail": "尚未配置 Boss直聘 cookie：请先粘贴保存再测试"}
    try:
        async with httpx.AsyncClient(
            transport=_VERIFY_TRANSPORT,
            timeout=_VERIFY_TIMEOUT,
            follow_redirects=False,
        ) as client:
            resp = await client.get(_VERIFY_URL, headers={"Cookie": raw, "User-Agent": _VERIFY_UA})
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"网络错误：{exc}"}
    return _judge_verify(resp)


# ---------------- 扩展诊断遥测（排查期临时端点，采集链路稳定后删除） ----------------


@router.post("/api/debug")
async def debug_telemetry(request: Request) -> dict:
    """扩展 content script 上报的采集诊断（wapi code / DOM 卡片数 / 错误）。

    仅写入服务日志用于排查；非正式 API，D25 采集链路稳定后删除。
    """
    try:
        body = await request.json()
        print(f"[TF-DEBUG] {body.get('kind', '?')} {body}", flush=True)
    except Exception as exc:  # noqa: BLE001 — 遥测绝不因解析异常打断
        print(f"[TF-DEBUG] parse-fail {exc}", flush=True)
    return {"ok": True}
