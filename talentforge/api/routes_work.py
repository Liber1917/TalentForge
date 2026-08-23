"""作品路由（M5 spec §4）：POST /api/work/fetch、GET /api/work/artifacts、
POST /api/work/claims、POST /api/work/dismiss。

fetch 并发调三源（单源 WorkSourceError → warnings 降级，不阻断其他源），
入库前对 github strong 候选跑内容探针（D29：documentation 强降 normal），
统一 upsert 进 WorkStore（模块级 ARTIFACTS_PATH 引用，测试可 monkeypatch）。
claims 把 artifact 生成 active 主张写入画像（spec §1.3：state="active" +
sources[0]={kind:"work", ref} + evidence_count=1，grade→confidence 映射；
同文本去重走 claim_id_for）；dismiss 驳回后不再生成主张（store 幂等）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from talentforge.api.common import claim_id_for, load_profile, save_profile
from talentforge.domain.profile import ClaimSource, NarrativeClaim, Profile
from talentforge.domain.work import WorkArtifact
from talentforge.llm.client import LLMClient
from talentforge.sources.content_probe import apply_probe_to_artifact, probe_content
from talentforge.sources.work_sources import (
    ArxivSource,
    GiteeSource,
    GitHubSource,
    WorkSourceError,
)
from talentforge.work import store as work_store
from talentforge.work.store import WorkStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["work"])

# spec §1.3：grade → confidence 映射（strong=0.9/normal=0.7/weak=0.5）
_GRADE_CONFIDENCE = {"strong": 0.9, "normal": 0.7, "weak": 0.5}
_GRADE_ZH = {"strong": "强", "normal": "普通", "weak": "弱"}
_PLATFORM_ZH = {"github": "GitHub", "gitee": "Gitee", "arxiv": "arXiv"}


class WorkFetchRequest(BaseModel):
    """fetch body：三个源任意组合（空串 = 不拉该源）。"""

    github_user: str = ""
    gitee_user: str = ""
    arxiv_author: str = ""


class WorkClaimsRequest(BaseModel):
    """claims body：按 id 列表或 all=True 全量（排除已驳回）。"""

    artifact_ids: list[str] = Field(default_factory=list)
    all: bool = False


class WorkDismissRequest(BaseModel):
    artifact_id: str


def _repo_claim_text(artifact: WorkArtifact) -> str:
    """repo 主张模板："GitHub 项目 {title}（{主语言}，{commits} commits，{grade 中文}信号）"。"""
    facts = artifact.facts or {}
    parts = [
        str(facts.get("language") or ""),
        f"{facts.get('commits', 0)} commits",
        f"{_GRADE_ZH.get(artifact.grade, '普通')}信号",
    ]
    label = _PLATFORM_ZH.get(artifact.platform, artifact.platform)
    return f"{label} 项目 {artifact.title}（{'，'.join(p for p in parts if p)}）"


def _paper_claim_text(artifact: WorkArtifact) -> str:
    """paper 主张模板："arXiv 论文《{title}》（{year}，{一作与否}{venue}）"。"""
    facts = artifact.facts or {}
    authors = [str(a) for a in facts.get("authors") or []]
    is_first = bool(authors) and str(facts.get("first_author") or "") == authors[0]
    role = "一作" if is_first else "合作者"
    venue = str(facts.get("venue") or "")
    inner = f"{role}，{venue}" if venue else role
    return f"arXiv 论文《{artifact.title}》（{facts.get('year', 0)}，{inner}）"


def _claim_text(artifact: WorkArtifact) -> str:
    if artifact.kind == "paper":
        return _paper_claim_text(artifact)
    return _repo_claim_text(artifact)


def _to_claim(artifact: WorkArtifact) -> NarrativeClaim:
    return NarrativeClaim(
        text=_claim_text(artifact),
        state="active",
        evidence_count=1,
        confidence=_GRADE_CONFIDENCE.get(artifact.grade, 0.5),
        sources=[ClaimSource(kind="work", ref=artifact.artifact_id)],
    )


async def _apply_content_probe(
    artifacts: list[WorkArtifact], llm: LLMClient
) -> list[WorkArtifact]:
    """github strong 候选逐条跑内容探针并联动分级（D29）；单条失败跳过不阻断。

    probe_content 自身软失败已返回 None（未配置/网络/解析），此处 try 仅兜
    注入替身/实现缺陷抛错；降级映射在 apply_probe_to_artifact 纯函数内
    （LLM 永不直接定级）。
    """
    probed: list[WorkArtifact] = []
    for artifact in artifacts:
        if artifact.platform != "github" or artifact.grade != "strong":
            probed.append(artifact)
            continue
        full_name = artifact.artifact_id.split(":", 1)[-1]
        try:
            probe = await probe_content(full_name, llm)
        except Exception as exc:
            logger.warning("内容探针异常，跳过 %s: %s", artifact.artifact_id, exc)
            probe = None
        probed.append(apply_probe_to_artifact(artifact, probe))
    return probed


@router.post("/api/work/fetch")
async def fetch_works(body: WorkFetchRequest, request: Request) -> dict:
    """三源并发拉取 + 统一入库；单源 WorkSourceError 记 warnings 不阻断。

    total_fetched = 本次成功拉取的 artifact 总数（跨源合并）；
    added = WorkStore.upsert_all 返回的新增条数（已存在按更新计）；
    入库前对 github strong 候选跑内容探针（D29），降级结果直接入库
    （added 计数语义不变）。
    """
    tasks: list[tuple[str, Coroutine[Any, Any, list[WorkArtifact]]]] = []
    if body.github_user:
        tasks.append(("github", GitHubSource().fetch_user_works(body.github_user)))
    if body.gitee_user:
        tasks.append(("gitee", GiteeSource().fetch_user_works(body.gitee_user)))
    if body.arxiv_author:
        tasks.append(("arxiv", ArxivSource().fetch_author_papers(body.arxiv_author)))

    artifacts: list[WorkArtifact] = []
    warnings: list[str] = []
    if tasks:
        results = await asyncio.gather(*(coro for _, coro in tasks), return_exceptions=True)
        for (name, _), result in zip(tasks, results, strict=True):
            if isinstance(result, WorkSourceError):
                warnings.append(f"{name}: {result}")
            elif isinstance(result, BaseException):
                raise result
            else:
                artifacts.extend(result)

    artifacts = await _apply_content_probe(artifacts, request.app.state.llm)
    added = WorkStore(work_store.ARTIFACTS_PATH).upsert_all(artifacts)
    return {
        "ok": True,
        "total_fetched": len(artifacts),
        "added": added,
        "warnings": warnings,
    }


@router.get("/api/work/artifacts")
def list_artifacts() -> dict:
    """全部作品（含已驳回，校对卡片按 dismissed 过滤）+ 驳回 id 列表。"""
    store = WorkStore(work_store.ARTIFACTS_PATH)
    artifacts = store.list_all()
    dismissed = [a.artifact_id for a in artifacts if store.is_dismissed(a.artifact_id)]
    return {
        "artifacts": [a.model_dump(mode="json") for a in artifacts],
        "dismissed": dismissed,
    }


@router.post("/api/work/claims")
def post_work_claims(body: WorkClaimsRequest) -> dict:
    """artifacts → active 主张写入画像（驳回的跳过；同文本去重 skipped 计数）。

    画像文件缺失时空画像兜底（同 feedback 路由风格，不 404）。
    """
    store = WorkStore(work_store.ARTIFACTS_PATH)
    artifacts = store.list_all()
    if body.all:
        targets = [a for a in artifacts if not store.is_dismissed(a.artifact_id)]
    else:
        wanted = set(body.artifact_ids)
        targets = [
            a
            for a in artifacts
            if a.artifact_id in wanted and not store.is_dismissed(a.artifact_id)
        ]

    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = Profile(name="")

    existing_ids = {claim_id_for(c.text) for c in profile.narrative_claims}
    written = 0
    skipped = 0
    for artifact in targets:
        claim = _to_claim(artifact)
        claim_id = claim_id_for(claim.text)
        if claim_id in existing_ids:
            skipped += 1
            continue
        profile.narrative_claims.append(claim)
        existing_ids.add(claim_id)
        written += 1

    save_profile(profile)
    return {"ok": True, "written": written, "skipped": skipped}


@router.post("/api/work/dismiss")
def post_work_dismiss(body: WorkDismissRequest) -> dict:
    """驳回作品（幂等）：该 artifact 不再用于生成主张（spec §1.3 防线 c）。"""
    WorkStore(work_store.ARTIFACTS_PATH).dismiss(body.artifact_id)
    return {"ok": True}
