"""画像路由：GET /api/profile（契约直出）、POST /api/profile/resume-review（抽取校对）、
GET /api/profile/export（完整 profile 下载）。

profile 从文件加载（TALENTFORGE_PROFILE_PATH 覆盖，缺省 docs/demo/profile.json）；
文件缺失时用 DefaultProfileEngine 构建（LLM 失败回退最小 Profile，不 500）。
resume-review 用 resume_io 抽取文本（新薄层：轻量规则解析字段，见 _diff_items 文档）。
"""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from talentforge.api.common import load_profile, profile_contract
from talentforge.domain.profile import Profile
from talentforge.profile.engine import DefaultProfileEngine
from talentforge.profile.resume_io import extract_resume_text

router = APIRouter(tags=["profile"])

# 轻量技能词表：抽取校对用，非穷举（deviation：resume 解析为规则启发，非 LLM 结构化抽取）
_SKILL_VOCAB: tuple[str, ...] = (
    "Python", "Go", "Golang", "Java", "SQL", "Redis", "Docker", "Kubernetes", "K8s",
    "分布式", "消息队列", "后端", "微服务", "Flask", "Django", "FastAPI", "Rust", "C++",
    "React", "Vue",
)
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*年")


@router.get("/api/profile")
async def get_profile(request: Request) -> dict:
    """画像直出：narrative 三轨 + utility_preferences + structural_position + narrative_claims。"""
    state = request.app.state
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = await _build_profile(state)
    return profile_contract(profile)


async def _build_profile(state: Any) -> Profile:
    """画像文件缺失时用 DefaultProfileEngine 构建；LLM 失败回退最小 Profile。"""
    engine = DefaultProfileEngine(llm=state.llm)
    try:
        return await engine.build_profile({"name": "候选人", "resume_text": ""})
    except Exception:
        return Profile(name="候选人")


@router.post("/api/profile/resume-review")
async def resume_review(request: Request) -> dict:
    """简历抽取校对：resume_io 抽取文本 → diff 视图（原文 vs 解析字段）。"""
    text, filename = await _read_resume(request)
    if not text:
        raise HTTPException(status_code=400, detail="需要 resume_file 路径或上传简历文件")
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = None
    return {"file": filename, "items": _diff_items(text, profile)}


@router.get("/api/profile/export")
def export_profile(request: Request) -> JSONResponse:
    """导出完整 profile JSON（Content-Disposition 触发下载）。"""
    profile = load_profile()
    return JSONResponse(
        content=profile.model_dump(),
        headers={"Content-Disposition": 'attachment; filename="talentforge-profile.json"'},
    )


async def _read_resume(request: Request) -> tuple[str, str]:
    """解析简历来源：multipart 的 file 字段或 JSON body 的 resume_file 路径。"""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(status_code=400, detail="multipart 请求需带 file 字段")
        filename = upload.filename or ""
        if not filename:
            raise HTTPException(status_code=400, detail="multipart 请求需带 file 字段")
        suffix = Path(filename).suffix or ".txt"
        tmp = Path(tempfile.gettempdir()) / f"tf_resume_{uuid.uuid4().hex}{suffix}"
        try:
            data = await upload.read()
            tmp.write_bytes(data)
            return extract_resume_text(tmp), filename
        finally:
            tmp.unlink(missing_ok=True)
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="需要 resume_file 路径或上传简历文件") from exc
    resume_file = body.get("resume_file")
    if not resume_file:
        raise HTTPException(status_code=400, detail="需要 resume_file 路径或上传简历文件")
    path = Path(str(resume_file))
    return extract_resume_text(path), path.name


def _guess_identity(text: str) -> str:
    """一句话定位启发：取首个非空行（去 markdown 标题符）。"""
    for line in text.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return cleaned[:80]
    return ""


def _guess_skills(text: str) -> list[str]:
    """技能启发：与词表做子串匹配（保序去重）。"""
    return [skill for skill in _SKILL_VOCAB if skill in text]


def _guess_years(text: str) -> str:
    """工作年限启发：匹配 N年 且 N∈[0,20]（过滤年份类误报，如 2026年）。"""
    for match in _YEARS_RE.finditer(text):
        value = float(match.group(1))
        if 0 <= value <= 20:
            return f"{value:g} 年"
    return ""


def _diff_items(text: str, profile: Profile | None) -> list[dict[str, str]]:
    """组装 diff 视图行：原文（当前画像值）vs 抽取（简历启发解析）。"""
    original_identity = ""
    original_skills: list[str] = []
    original_years = ""
    if profile is not None:
        original_identity = profile.narrative.identity
        original_skills = list(profile.skills)
        if profile.years_experience:
            original_years = f"{profile.years_experience:g} 年"
    return [
        {
            "field": "identity",
            "label": "一句话定位",
            "original": original_identity,
            "extracted": _guess_identity(text),
        },
        {
            "field": "skills",
            "label": "技能",
            "original": " · ".join(original_skills),
            "extracted": " · ".join(_guess_skills(text)),
        },
        {
            "field": "years_experience",
            "label": "工作年限",
            "original": original_years,
            "extracted": _guess_years(text),
        },
        {
            "field": "full_text",
            "label": "简历全文",
            "original": "",
            "extracted": text,
        },
    ]
