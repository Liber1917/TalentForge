"""作品源采集器（M5 spec §3）：GitHub / Gitee / arXiv → WorkArtifact。

LLM 零参与（D23 防线 a）：只拉取结构化事实，分级走 work_grading 规则表；
单源失败抛 WorkSourceError，由上层编排（T2 路由）按单源粒度捕获降级。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Literal, cast

import httpx

from talentforge.domain.work import WorkArtifact, WorkGrade
from talentforge.sources.work_grading import grade_paper, grade_repo, match_ccf_venue

logger = logging.getLogger(__name__)

UA = "TalentForge/0.1 (personal job-assistant)"
TIMEOUT = 20.0
GITHUB_API = "https://api.github.com"
GITEE_API = "https://gitee.com/api/v5"
ARXIV_API = "http://export.arxiv.org/api/query"

_GITHUB_LIMIT_MSG = "GitHub 限流，请配置 TALENTFORGE_GITHUB_TOKEN"
_GITEE_LIMIT_MSG = "Gitee 限流，请稍后重试"

_ATOM = "{http://www.w3.org/2005/Atom}"

RepoPlatform = Literal["github", "gitee"]


class WorkSourceError(RuntimeError):
    """作品源采集失败（限流/网络/形状异常）；上层按单源粒度捕获降级。"""


def _commit_date(commit: Any) -> str:
    """commit 对象 → 作者日期 ISO 串（GitHub/Gitee 同构，缺失返回空）。"""
    if not isinstance(commit, dict):
        return ""
    node = commit.get("commit")
    if not isinstance(node, dict):
        return ""
    author = node.get("author")
    if not isinstance(author, dict):
        return ""
    return str(author.get("date") or "")


def _last_page_from_link(link_header: str) -> int:
    """Link header → rel="last" 页码（per_page=1 时即 commit 总数）；无 last 返回 1。"""
    for m in re.finditer(r'<([^>]+)>\s*;\s*rel="last"', link_header):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(m.group(1)).query)
        try:
            return max(1, int(query.get("page", ["1"])[0]))
        except ValueError:
            return 1
    return 1


def _span_days(first_iso: str, last_iso: str) -> int:
    """首末 commit ISO 时间跨度（天）；缺失/无法解析返回 0。"""
    if not first_iso or not last_iso:
        return 0
    try:
        first = datetime.fromisoformat(first_iso.replace("Z", "+00:00"))
        last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return abs((last - first).days)


def parse_arxiv_feed(xml_text: str) -> list[dict[str, Any]]:
    """arXiv Atom feed → entry dict 列表（title/summary 空白折叠，作者保序）。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise WorkSourceError(f"arXiv 响应 XML 解析失败: {e}") from e
    entries: list[dict[str, Any]] = []
    for node in root.findall(_ATOM + "entry"):
        entries.append(
            {
                "title": " ".join((node.findtext(_ATOM + "title") or "").split()),
                "summary": " ".join((node.findtext(_ATOM + "summary") or "").split()),
                "authors": [
                    (a.findtext(_ATOM + "name") or "").strip()
                    for a in node.findall(_ATOM + "author")
                ],
                "published": node.findtext(_ATOM + "published") or "",
                "id": node.findtext(_ATOM + "id") or "",
            }
        )
    return entries


async def _fetch_json_list(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any] | None,
    rate_limit_msg: str,
) -> list[dict[str, Any]]:
    resp = await client.get(url, params=params)
    if resp.status_code in (403, 429):
        raise WorkSourceError(rate_limit_msg)
    if resp.status_code >= 400:
        raise WorkSourceError(f"作品源请求失败: HTTP {resp.status_code} {url}")
    data = resp.json()
    if not isinstance(data, list):
        raise WorkSourceError(f"作品源响应形状异常（需 JSON 数组）: {url}")
    return [r for r in data if isinstance(r, dict)]


async def _languages(client: httpx.AsyncClient, url: str) -> dict[str, int]:
    """语言分布（bytes）；可选富化字段，失败软降级为空 dict 不阻断采集。"""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("语言分布获取失败: %s", url)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items()}


async def _commit_summary(
    client: httpx.AsyncClient, api_base: str, full_name: str, rate_limit_msg: str
) -> tuple[int, str, str]:
    """(commits 总数, 首条时间, 最新时间)。

    per_page=1 列表第一条 = 最新 commit；Link header rel="last" 页码 = 总数
    （无 Link = 1 条）；页码 == 总数 时取该页即最早一条。
    单仓库详情偶发失败软降级为 (0, "", "") 不毁整批（实测 GitHub commits
    接口间歇 504——repos 列表已带 stars/forks/language，缺 commits 只是
    分级保守化）；限流(403/429)仍按源级错误上抛。
    """
    url = f"{api_base}/repos/{full_name}/commits"
    resp = await client.get(url, params={"per_page": 1})
    if resp.status_code == 409:
        return 0, "", ""  # 空仓库无 commits
    if resp.status_code in (403, 429):
        raise WorkSourceError(rate_limit_msg)
    if resp.status_code >= 400:
        logger.warning(
            "commits 概要获取失败(HTTP %s)，本仓库软降级: %s", resp.status_code, url
        )
        return 0, "", ""
    page = resp.json()
    if not isinstance(page, list) or not page:
        return 0, "", ""
    last_at = _commit_date(page[0])
    total = _last_page_from_link(resp.headers.get("link", ""))
    first_at = last_at
    if total > 1:
        resp_first = await client.get(url, params={"per_page": 1, "page": total})
        if resp_first.status_code >= 400:
            logger.warning(
                "最早 commit 获取失败(HTTP %s)，span 按 0 计: %s",
                resp_first.status_code,
                url,
            )
        else:
            oldest = resp_first.json()
            if isinstance(oldest, list) and oldest:
                first_at = _commit_date(oldest[0])
    return total, first_at, last_at


async def _repo_facts(
    client: httpx.AsyncClient,
    api_base: str,
    repo: dict[str, Any],
    rate_limit_msg: str,
    is_fork: bool,
) -> dict[str, Any]:
    full_name = str(repo.get("full_name") or "")
    languages = await _languages(client, f"{api_base}/repos/{full_name}/languages")
    commits, first_at, last_at = await _commit_summary(client, api_base, full_name, rate_limit_msg)
    language = str(repo.get("language") or "")
    if not language and languages:
        language = max(languages, key=lambda k: languages[k])
    return {
        "stars": int(repo.get("stargazers_count") or 0),
        "forks": int(repo.get("forks_count") or 0),
        "is_fork": is_fork,
        "language": language,
        "languages": languages,
        "commits": commits,
        "span_days": _span_days(first_at, last_at),
        "pushed_at": str(repo.get("pushed_at") or ""),
    }


def _repo_artifact(
    platform: RepoPlatform, repo: dict[str, Any], facts: dict[str, Any]
) -> WorkArtifact:
    raw_grade, reasons = grade_repo(facts)
    return WorkArtifact(
        artifact_id=f"{platform}:{repo.get('full_name', '')}",
        platform=platform,
        kind="repo",
        title=str(repo.get("name") or ""),
        url=str(repo.get("html_url") or ""),
        facts=facts,
        grade=cast(WorkGrade, raw_grade),
        grade_reasons=reasons,
    )


class GitHubSource:
    """GitHub 用户仓库采集：repos（type=owner，fork 只进 facts 不排除）+ 详情。"""

    def __init__(
        self,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token or os.environ.get("TALENTFORGE_GITHUB_TOKEN", "")
        self._transport = transport

    async def fetch_user_works(self, username: str) -> list[WorkArtifact]:
        headers = {"User-Agent": UA}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=TIMEOUT, headers=headers
            ) as client:
                repos = await _fetch_json_list(
                    client,
                    f"{GITHUB_API}/users/{username}/repos",
                    params={"per_page": 100, "type": "owner"},
                    rate_limit_msg=_GITHUB_LIMIT_MSG,
                )
                facts_list = await asyncio.gather(
                    *(
                        _repo_facts(
                            client,
                            GITHUB_API,
                            repo,
                            rate_limit_msg=_GITHUB_LIMIT_MSG,
                            is_fork=bool(repo.get("fork")),
                        )
                        for repo in repos
                    )
                )
        except WorkSourceError:
            raise
        except httpx.HTTPError as e:
            raise WorkSourceError(f"GitHub 网络请求失败: {e}") from e
        return [
            _repo_artifact("github", repo, facts)
            for repo, facts in zip(repos, facts_list, strict=True)
        ]


class GiteeSource:
    """Gitee 用户仓库采集（API v5，无 token）；fork 经 fork/parent 字段识别。"""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_user_works(self, username: str) -> list[WorkArtifact]:
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=TIMEOUT, headers={"User-Agent": UA}
            ) as client:
                repos = await _fetch_json_list(
                    client,
                    f"{GITEE_API}/users/{username}/repos",
                    params={"per_page": 100},
                    rate_limit_msg=_GITEE_LIMIT_MSG,
                )
                facts_list = await asyncio.gather(
                    *(
                        _repo_facts(
                            client,
                            GITEE_API,
                            repo,
                            rate_limit_msg=_GITEE_LIMIT_MSG,
                            is_fork=bool(repo.get("fork") or repo.get("parent")),
                        )
                        for repo in repos
                    )
                )
        except WorkSourceError:
            raise
        except httpx.HTTPError as e:
            raise WorkSourceError(f"Gitee 网络请求失败: {e}") from e
        return [
            _repo_artifact("gitee", repo, facts)
            for repo, facts in zip(repos, facts_list, strict=True)
        ]


class ArxivSource:
    """arXiv 作者论文采集：Atom feed → 论文 facts（venue 缺省空，grade 层封顶 normal）。"""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_author_papers(self, author: str) -> list[WorkArtifact]:
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=TIMEOUT, headers={"User-Agent": UA}
            ) as client:
                resp = await client.get(
                    ARXIV_API,
                    params={"search_query": f'au:"{author}"', "max_results": 50},
                )
        except httpx.HTTPError as e:
            raise WorkSourceError(f"arXiv 网络请求失败: {e}") from e
        if resp.status_code in (403, 429):
            raise WorkSourceError("arXiv 限流，请稍后重试")
        if resp.status_code >= 400:
            raise WorkSourceError(f"arXiv 请求失败: HTTP {resp.status_code}")
        artifacts: list[WorkArtifact] = []
        for entry in parse_arxiv_feed(resp.text):
            facts = {
                "authors": entry["authors"],
                "first_author": author,  # 目标作者（一作判定：== authors[0]）
                "year": _year_of(entry["published"]),
                "venue": match_ccf_venue(entry["title"]),  # 标题含会议名 → 查表
                "summary": entry["summary"][:300],
            }
            raw_grade, reasons = grade_paper(facts)
            arxiv_id = entry["id"].rstrip("/").split("/abs/")[-1]
            artifacts.append(
                WorkArtifact(
                    artifact_id=f"arxiv:{arxiv_id}",
                    platform="arxiv",
                    kind="paper",
                    title=entry["title"],
                    url=entry["id"],
                    facts=facts,
                    grade=cast(WorkGrade, raw_grade),
                    grade_reasons=reasons,
                )
            )
        return artifacts


def _year_of(published: str) -> int:
    try:
        return int(published[:4])
    except (TypeError, ValueError):
        return 0
