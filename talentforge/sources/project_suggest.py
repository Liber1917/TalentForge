"""项目推荐器（M6 spec §2）：gap 技能 → GitHub search → 规则筛 → 缓存。

信号投资循环的"推荐"环（D26）：matcher 产出 gap（如"缺 K8s 实践"）后，
按 gap 关键词搜 GitHub 优质 repo 供用户参与（fork/PR），回流走 M5 作品源。
LLM 零参与（D23 防线 b）：R-s1~R-s5 纯规则筛；限流应对走 24h JSON 缓存
（search API 未认证 10 req/min）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from talentforge.sources.work_sources import GITHUB_API, TIMEOUT, UA, WorkSourceError

logger = logging.getLogger(__name__)

_GITHUB_SEARCH_LIMIT_MSG = "GitHub 搜索限流，请配置 TALENTFORGE_GITHUB_TOKEN"

# 相对 cwd（同 work.store.ARTIFACTS_PATH 风格；data/ 已 gitignore），可 monkeypatch；
# env TALENTFORGE_SUGGESTIONS_PATH 可覆盖
SUGGESTIONS_PATH = Path("data/suggestions.json")

# spec §2.1 规则筛阈值
MIN_STARS = 100          # R-s1 下限：低于视为冷门剔除
BIG_STARS = 50000        # R-s1 上限：超过标记"超大项目，参考为主"
ACTIVE_WINDOW_DAYS = 30  # R-s2 活跃窗口（天）
MAX_OPEN_ISSUES = 500    # R-s3 维护能力上限
SEARCH_PER_PAGE = 15     # search API 单页条数（筛后留余量）
SUGGEST_LIMIT = 5        # 最终返回上限
SUGGESTIONS_TTL = timedelta(hours=24)


def _resolve_path() -> Path:
    env = os.environ.get("TALENTFORGE_SUGGESTIONS_PATH", "")
    return Path(env) if env else SUGGESTIONS_PATH


def _int(value: Any) -> int:
    """容错取整（缺失/垃圾值按 0，规则筛按最保守分支处理）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def search_repos(
    gap_skill: str, language: str = "", transport: httpx.AsyncBaseTransport | None = None
) -> list[dict[str, Any]]:
    """GitHub search/repositories → items 原始 dict 列表（容错形状，只滤 dict）。

    q = gap[+language:xx]，sort=stars desc；复用 work_sources 约定
    （UA / TALENTFORGE_GITHUB_TOKEN / TIMEOUT）；403/429 → 限流错误，
    其余 4xx/网络/解析失败 → WorkSourceError（上层按 gap 粒度捕获降级）。
    """
    query = gap_skill.strip()
    if language.strip():
        query += f"+language:{language.strip()}"
    headers = {"User-Agent": UA}
    token = os.environ.get("TALENTFORGE_GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=TIMEOUT, headers=headers
        ) as client:
            resp = await client.get(
                f"{GITHUB_API}/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": SEARCH_PER_PAGE,
                },
            )
    except httpx.HTTPError as e:
        raise WorkSourceError(f"GitHub 搜索网络请求失败: {e}") from e
    if resp.status_code in (403, 429):
        raise WorkSourceError(_GITHUB_SEARCH_LIMIT_MSG)
    if resp.status_code >= 400:
        raise WorkSourceError(f"GitHub 搜索请求失败: HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as e:
        raise WorkSourceError(f"GitHub 搜索响应解析失败: {e}") from e
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [r for r in items if isinstance(r, dict)]


def _is_active(pushed_at: str, now: datetime) -> bool:
    """R-s2：pushed_at 在 ACTIVE_WINDOW_DAYS 天内；缺失/无法解析按不活跃剔除。"""
    if not pushed_at:
        return False
    try:
        pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if pushed.tzinfo is None:
        pushed = pushed.replace(tzinfo=timezone.utc)
    return now - pushed <= timedelta(days=ACTIVE_WINDOW_DAYS)


def _to_suggestion(repo: dict[str, Any], keyword_hit: bool, gap_skill: str) -> dict[str, Any]:
    """repo → 推荐卡字段（why 为命中规则人话，如"活跃·规模适中·与 Kubernetes 相关"）。"""
    stars = _int(repo.get("stargazers_count"))
    parts = ["超大项目，参考为主" if stars > BIG_STARS else "规模适中", "活跃"]
    parts.append(f"与 {gap_skill} 相关" if keyword_hit else "描述完整")
    return {
        "full_name": str(repo.get("full_name") or ""),
        "url": str(repo.get("html_url") or ""),
        "stars": stars,
        "description": str(repo.get("description") or ""),
        "language": str(repo.get("language") or ""),
        "pushed_at": str(repo.get("pushed_at") or ""),
        "why": "·".join(parts),
    }


def filter_apt_projects(repos: list[dict[str, Any]], gap_skill: str) -> list[dict[str, Any]]:
    """规则筛（spec §2.1 R-s1~R-s5，纯函数、LLM 零参与）。

    R-s1 stars<100 剔除，>50000 保留但 why 标记"超大项目，参考为主"；
    R-s2 pushed_at 30 天内；R-s3 open_issues_count<500；R-s4 description
    非空且包含 gap 关键词（大小写不敏感）——若严格版全被关键词剔光，
    放宽为"description 非空"（推荐位不空转）；R-s5 fork 剔除。
    输出按 stars 降序最多 SUGGEST_LIMIT 条。
    """
    now = datetime.now(timezone.utc)
    keyword = gap_skill.strip().lower()
    # base：过 R-s1/s2/s3/s5 且 description 非空（R-s4 前半），附关键词命中标记
    base: list[tuple[dict[str, Any], bool]] = []
    for repo in repos:
        if not isinstance(repo, dict) or bool(repo.get("fork")):
            continue  # R-s5（含形状容错：非 dict 一并跳过）
        stars = _int(repo.get("stargazers_count"))
        if stars < MIN_STARS:
            continue  # R-s1 下限
        if _int(repo.get("open_issues_count")) >= MAX_OPEN_ISSUES:
            continue  # R-s3
        if not _is_active(str(repo.get("pushed_at") or ""), now):
            continue  # R-s2
        description = str(repo.get("description") or "")
        if not description:
            continue  # R-s4 前半
        base.append((repo, keyword in description.lower()))
    strict = [(repo, hit) for repo, hit in base if hit]
    pool = strict if strict else base  # R-s4 放宽回退
    items = [_to_suggestion(repo, hit, gap_skill) for repo, hit in pool]
    items.sort(key=lambda item: item["stars"], reverse=True)
    return items[:SUGGEST_LIMIT]


def _read_cache() -> dict[str, Any]:
    """读 suggestions.json；缺失/损坏（JSON 坏/形状坏）按空 dict（文件容错）。"""
    try:
        data = json.loads(_resolve_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cache_fresh(entry: dict[str, Any]) -> bool:
    """TTL 校验：cached_at 距今 < SUGGESTIONS_TTL；缺失/无法解析按过期。"""
    try:
        cached_at = datetime.fromisoformat(str(entry.get("cached_at") or ""))
    except ValueError:
        return False
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - cached_at < SUGGESTIONS_TTL


def _write_cache(gap_skill: str, items: list[dict[str, Any]]) -> None:
    """merge 写入 {gap_skill: {items, cached_at}}；写失败仅告警不阻断推荐。"""
    cache = _read_cache()
    cache[gap_skill] = {
        "items": items,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _resolve_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        logger.warning("推荐缓存写入 %s 失败: %s", path, e)


async def suggest_projects(
    gap_skill: str, language: str = "", transport: httpx.AsyncBaseTransport | None = None
) -> list[dict[str, Any]]:
    """gap → 推荐 repo 列表（缓存优先，TTL 24h；未命中才 search + 规则筛）。"""
    entry = _read_cache().get(gap_skill)
    if isinstance(entry, dict):
        items = entry.get("items")
        if isinstance(items, list) and _cache_fresh(entry):
            return [i for i in items if isinstance(i, dict)]
    repos = await search_repos(gap_skill, language=language, transport=transport)
    items = filter_apt_projects(repos, gap_skill)
    _write_cache(gap_skill, items)
    return items
