"""简历产出路由（M5 spec §6 最小版）：GET /cv → Jinja2 A4 模板渲染（旧 /resume 路径 302 跳转，
避免与 GSD /gsd-resume-work 语义混淆——D28 命名分域）。

easyCV 借鉴（docs/research/easycv-teardown.md）：数据→模板→A4→打印，
window.print + print CSS 零依赖导出 PDF。数据聚合不走 LLM：
- profile：load_profile()（文件缺失 → 占位提示页，不 500）
- works：WorkStore(ARTIFACTS_PATH).list_all()，按 grade strong>normal>weak 排序，
  排除未知 grade；已驳回条目不上简历（store 契约：展示层按 is_dismissed 过滤）
- claims：active 态主张 → "能力主张"段（trial/archived 不上简历）

模板放包内 talentforge/templates/（不经 web/ 静态目录——静态挂载只服务资产，
页面由路由渲染更干净，Jinja2Templates(directory=...) 指向包内目录）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from talentforge.api.common import format_salary, load_profile
from talentforge.domain.profile import Profile
from talentforge.domain.work import WorkArtifact
from talentforge.work import store as work_store
from talentforge.work.store import WorkStore

router = APIRouter(tags=["resume"])

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

# grade 展示序（strong>normal>weak，spec §2）+ 中文徽章字（词表同 routes_work）
_GRADE_RANK = {"strong": 0, "normal": 1, "weak": 2}
_GRADE_ZH = {"strong": "强信号", "normal": "普通信号", "weak": "弱信号"}
_PLATFORM_ZH = {"github": "GitHub", "gitee": "Gitee", "arxiv": "arXiv"}
_KIND_ZH = {"repo": "仓库", "paper": "论文"}


def _facts_summary(artifact: WorkArtifact) -> str:
    """facts → 一行摘要：repo=语言·commits·stars；paper=一作与否·venue·年份。"""
    facts = artifact.facts or {}
    parts: list[str] = []
    if artifact.kind == "paper":
        authors = [str(a) for a in facts.get("authors") or []]
        is_first = bool(authors) and str(facts.get("first_author") or "") == authors[0]
        parts.append("一作" if is_first else "合作者")
        if facts.get("venue"):
            parts.append(str(facts["venue"]))
        if facts.get("year"):
            parts.append(f"{facts['year']} 年")
        return " · ".join(parts)
    if facts.get("language"):
        parts.append(str(facts["language"]))
    if facts.get("commits"):
        parts.append(f"{facts['commits']} commits")
    if facts.get("stars"):
        parts.append(f"{facts['stars']} stars")
    return " · ".join(parts)


def _salary_segment(profile: Profile) -> str:
    """薪资段展示：utility 偏好序（"30-40万 › 40万以上"）优先，缺省回落 salary_expectation。"""
    pref = profile.utility_preferences.get("salary")
    if pref is not None and pref.ordering:
        return " › ".join(pref.ordering)
    return format_salary(profile.salary_expectation)


@router.get("/cv", response_class=HTMLResponse)
def get_cv(request: Request) -> HTMLResponse:
    """A4 简历产出页：画像 + 作品 + active 主张聚合渲染（导出 PDF 走 window.print）。"""
    try:
        profile = load_profile()
    except FileNotFoundError:
        return _templates.TemplateResponse(
            request,
            "resume.html",
            {"basics": None, "works": [], "claims": []},
        )

    store = WorkStore(work_store.ARTIFACTS_PATH)
    artifacts = [
        a
        for a in store.list_all()
        if a.grade in _GRADE_RANK and not store.is_dismissed(a.artifact_id)
    ]
    artifacts.sort(key=lambda a: _GRADE_RANK[a.grade])
    works = [
        {
            "title": a.title,
            "url": a.url,
            "grade": a.grade,
            "grade_zh": _GRADE_ZH[a.grade],
            "facts_summary": _facts_summary(a),
            "platform_zh": _PLATFORM_ZH.get(a.platform, a.platform),
            "kind_zh": _KIND_ZH.get(a.kind, a.kind),
        }
        for a in artifacts
    ]

    basics = {
        "name": profile.name,
        "identity": profile.narrative.identity,
        "email": profile.email or "",
        "skills": list(profile.skills),
        "desired_roles": list(profile.desired_roles),
        "locations": list(profile.preferred_locations),
        "salary": _salary_segment(profile),
    }
    claims = [c.text for c in profile.narrative_claims if c.state == "active"]
    return _templates.TemplateResponse(
        request,
        "resume.html",
        {"basics": basics, "works": works, "claims": claims},
    )


@router.get("/resume", include_in_schema=False)
def resume_legacy_redirect() -> RedirectResponse:
    """旧路径兼容：/resume → /cv（302，书签友好）。"""
    return RedirectResponse(url="/cv", status_code=302)
