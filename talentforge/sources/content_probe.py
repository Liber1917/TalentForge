"""内容探针（D29）：证据采集 → LLM 内容分类 → 分级联动，补规则的度量盲区。

实证盲区（Liber1917/Embedded_training_IEST）：35 commits / 717 天 span 被 R3
判 strong，但仓库实为培训资料收集（路线图 SVG / 学习资源目录 / vendored 课程
模板）——规则看得见度量、看不见内容。探针对 strong 候选补采三样便宜证据
（README 头 / 顶层条目 / 最近提交信息首行），LLM 引用证据分类 content_type，
规则表再把分类映射为分级（documentation 封顶 normal，R9）；LLM 永不直接
定级（D23 防线 b），证据随 facts.content_probe 上卡供用户校对（防线 c）。
探针任何失败（网络 / LLM / 解析 / 形状）一律软降级返回 None，绝不阻断
采集主流程。
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from talentforge.domain.work import WorkArtifact
from talentforge.llm.client import LLMClient
from talentforge.llm.json_utils import extract_json
from talentforge.sources.work_sources import GITHUB_API, TIMEOUT, UA

logger = logging.getLogger(__name__)

# prompt-cache 约定（同 EVENT_TO_CLAIM_SYSTEM_PROMPT）：system 为模块级静态
# 常量、零变量；仓库名与全部证据都在 user message。
CONTENT_PROBE_SYSTEM_PROMPT = (
    "你是代码仓库内容分类器。根据用户消息给出的仓库证据（README 开头、顶层"
    "目录/文件列表、最近提交信息首行），判断仓库的主体内容类型。只输出一个"
    "JSON 对象，不要输出其他文字。格式："
    '{"content_type": "engineering|research|documentation|coursework|mixed", '
    '"confidence": 0到1的小数, "evidence": ["引用原文或文件名的短证据", ...], '
    '"summary": "一句话中文结论"}。判定标准：engineering=自研代码实现（源码'
    "为主体，README 描述自己构建的项目）；research=实验或论文复现且含自己"
    "编写的代码；documentation=学习资料/资源收集/路线图整理（代码为模板或 "
    "vendored 第三方，非作者实现）；coursework=课程作业；mixed=兼有多类。"
    "evidence 每条必须从给出的材料中引用原文或文件名，不允许编造；证据不足"
    "或相互矛盾时给低 confidence。summary 用中文。"
)

CONTENT_TYPES: frozenset[str] = frozenset(
    {"engineering", "research", "documentation", "coursework", "mixed"}
)

README_HEAD_CHARS = 2000  # README 证据只取头部
MAX_TOP_ENTRIES = 20      # 顶层条目上限
RECENT_COMMITS = 5        # 最近提交信息条数
MAX_EVIDENCE = 3          # 入库证据条数上限


async def _fetch_readme_head(client: httpx.AsyncClient, full_name: str) -> str:
    """README 头 README_HEAD_CHARS 字符（base64 解码）；404/失败软降级为空串。"""
    try:
        resp = await client.get(f"{GITHUB_API}/repos/{full_name}/readme")
        if resp.status_code >= 400:
            if resp.status_code != 404:
                logger.warning(
                    "README 获取失败(HTTP %s)，软降级为空: %s", resp.status_code, full_name
                )
            return ""
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("README 获取异常，软降级为空: %s", full_name)
        return ""
    if not isinstance(data, dict):
        return ""
    encoded = str(data.get("content") or "").replace("\n", "").replace("\r", "")
    try:
        decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except ValueError:  # binascii.Error / UnicodeDecodeError 均为 ValueError 子类
        return ""
    return decoded[:README_HEAD_CHARS]


async def _fetch_top_entries(client: httpx.AsyncClient, full_name: str) -> list[str]:
    """顶层条目 name(type) 列表（最多 MAX_TOP_ENTRIES 项）；失败软降级为空。"""
    try:
        resp = await client.get(f"{GITHUB_API}/repos/{full_name}/contents/")
        if resp.status_code >= 400:
            logger.warning(
                "顶层目录获取失败(HTTP %s)，软降级为空: %s", resp.status_code, full_name
            )
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("顶层目录获取异常，软降级为空: %s", full_name)
        return []
    if not isinstance(data, list):
        return []
    entries: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        kind = "dir" if item.get("type") == "dir" else "file"
        entries.append(f"{name}({kind})")
    return entries[:MAX_TOP_ENTRIES]


async def _fetch_recent_commits(client: httpx.AsyncClient, full_name: str) -> list[str]:
    """最近 RECENT_COMMITS 条提交信息首行；失败软降级为空。"""
    try:
        resp = await client.get(
            f"{GITHUB_API}/repos/{full_name}/commits", params={"per_page": RECENT_COMMITS}
        )
        if resp.status_code >= 400:
            logger.warning(
                "最近提交获取失败(HTTP %s)，软降级为空: %s", resp.status_code, full_name
            )
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("最近提交获取异常，软降级为空: %s", full_name)
        return []
    if not isinstance(data, list):
        return []
    messages: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        node = item.get("commit")
        if not isinstance(node, dict):
            continue
        first_line = str(node.get("message") or "").partition("\n")[0].strip()
        if first_line:
            messages.append(first_line)
    return messages


async def fetch_repo_evidence(
    full_name: str, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    """GitHub 三样证据：README 头 + 顶层条目 + 最近提交首行（软降级，不抛）。

    复用 work_sources 约定（UA / TALENTFORGE_GITHUB_TOKEN / TIMEOUT）；
    单端点失败只弃该端点，返回已得部分。
    """
    headers = {"User-Agent": UA}
    token = os.environ.get("TALENTFORGE_GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    evidence: dict[str, Any] = {"readme_head": "", "top_entries": [], "recent_commits": []}
    async with httpx.AsyncClient(
        transport=transport, timeout=TIMEOUT, headers=headers
    ) as client:
        evidence["readme_head"] = await _fetch_readme_head(client, full_name)
        evidence["top_entries"] = await _fetch_top_entries(client, full_name)
        evidence["recent_commits"] = await _fetch_recent_commits(client, full_name)
    return evidence


def _build_user_message(full_name: str, evidence: dict[str, Any]) -> str:
    """仓库名 + 三样证据 → user message（变量全在 user，system 零变量）。"""
    entries = evidence.get("top_entries") or []
    commits = evidence.get("recent_commits") or []
    entry_lines = "\n".join(f"- {str(item)}" for item in entries) or "（未获取到）"
    commit_lines = "\n".join(f"- {str(item)}" for item in commits) or "（未获取到）"
    return (
        f"仓库：{full_name}\n"
        "README 开头：\n"
        f"{str(evidence.get('readme_head') or '') or '（无 README）'}\n"
        "顶层目录/文件：\n"
        f"{entry_lines}\n"
        "最近提交信息首行：\n"
        f"{commit_lines}"
    )


async def probe_content(
    full_name: str,
    llm: LLMClient,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any] | None:
    """证据采集 → LLM 分类 → 形状校验；任何失败返回 None（探针绝不毁主流程）。

    返回 {"content_type", "confidence", "summary", "evidence"(≤3条)}；
    content_type 不在枚举或 evidence 非列表视为形状不对 → None。
    """
    try:
        evidence = await fetch_repo_evidence(full_name, transport=transport)
        if not any(evidence.values()):
            logger.info("三样证据全空（拉取失败或空仓库），探针跳过: %s", full_name)
            return None
        raw = await llm.chat(CONTENT_PROBE_SYSTEM_PROMPT, _build_user_message(full_name, evidence))
        data = extract_json(raw)
    except Exception as exc:  # LLM 未配置/网络/解析失败：探针不可用，不毁流程
        logger.warning("内容探针失败，跳过 %s: %s", full_name, exc)
        return None

    content_type = str(data.get("content_type") or "")
    if content_type not in CONTENT_TYPES:
        logger.warning("内容探针 content_type 非法(%r)，跳过: %s", content_type, full_name)
        return None
    evidence_items = data.get("evidence")
    if not isinstance(evidence_items, list):
        logger.warning("内容探针 evidence 形状异常，跳过: %s", full_name)
        return None
    cleaned = [str(item).strip() for item in evidence_items if isinstance(item, str)]
    cleaned = [item for item in cleaned if item][:MAX_EVIDENCE]
    try:
        confidence = min(1.0, max(0.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "content_type": content_type,
        "confidence": confidence,
        "summary": str(data.get("summary") or "").strip(),
        "evidence": cleaned,
    }


def apply_probe_to_artifact(artifact: WorkArtifact, probe: dict[str, Any] | None) -> WorkArtifact:
    """探针结果 → 作品条目分级联动（纯函数；LLM 不直接定级，规则查表映射）。

    probe None → 原样返回；content_type == "documentation" 且 grade == "strong"
    → 降 normal 并追加 R9 证据 reason；其余情形保持 grade、仅追加 R9 附注；
    facts 合并 content_probe（前端展示证据，用户可校对，D23 防线 c）。
    """
    if probe is None:
        return artifact
    result = artifact.model_copy(deep=True)
    content_type = str(probe.get("content_type") or "")
    summary = str(probe.get("summary") or "")
    evidence = [str(item) for item in (probe.get("evidence") or []) if str(item)]
    if content_type == "documentation" and result.grade == "strong":
        result.grade = "normal"
        first = evidence[0] if evidence else summary
        reason = f"R9: 内容探针判定资料收集型（证据：{first[:60]}）"
    else:
        reason = f"R9: 内容探针：{content_type}（{summary[:40]}）"
    result.grade_reasons = [*result.grade_reasons, reason]
    result.facts = {**result.facts, "content_probe": probe}
    return result
