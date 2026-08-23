"""M3 真端点共享工具：画像持久化、卡片契约序列化、判定缺省估算。

Task 7 各路由复用：
- profile 文件读写（TALENTFORGE_PROFILE_PATH 覆盖，缺省 docs/demo/profile.json）
- NarrativeClaim → ClaimCard 契约（claim_id 由文本哈希稳定导出，confirm/reject 依此定位）
- 岗位列表契约（verdict 取 decisions 缓存或缺省估算）+ 薪资展示
- 结构风险评估复用 field.risks.assess（不重写内部逻辑）
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from talentforge.domain.job import Job
from talentforge.domain.profile import NarrativeClaim, Profile, SalaryRange
from talentforge.field.risks import assess

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROFILE_PATH = _PACKAGE_ROOT / "docs" / "demo" / "profile.json"
RUNTIME_PROFILE_PATH = Path("data/profile.json")  # 相对 cwd（data/ 已 gitignore）
PROFILE_ENV = "TALENTFORGE_PROFILE_PATH"


def profile_path() -> Path:
    """画像读路径：env TALENTFORGE_PROFILE_PATH > 运行时 data/profile.json > 演示 fixture。

    演示 fixture（docs/demo/profile.json，git 跟踪）只作首次种子与离线演示——
    读链允许回落到它，写链永不落它（见 save_profile）。
    """
    env = os.environ.get(PROFILE_ENV)
    if env:
        return Path(env)
    if RUNTIME_PROFILE_PATH.exists():
        return RUNTIME_PROFILE_PATH
    return DEFAULT_PROFILE_PATH


def load_profile() -> Profile:
    """从画像文件加载 Profile；文件缺失抛 FileNotFoundError（调用方决定兜底）。"""
    path = profile_path()
    if not path.exists():
        raise FileNotFoundError(f"画像文件不存在: {path}")
    return Profile.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_profile(profile: Profile) -> None:
    """画像写路径：env 显式时写 env 路径，否则写运行时 data/profile.json。

    git 跟踪的演示 fixture 永不写入——用户真实主张/偏好回流只落 gitignored
    运行时文件（M5 教训：真实作品主张写入演示 fixture 曾打破契约测试）。
    """
    env = os.environ.get(PROFILE_ENV)
    path = Path(env) if env else RUNTIME_PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def claim_id_for(text: str) -> str:
    """主张文本 → 稳定 claim_id（sha1 前 12 位，确认/驳回按此定位，无持久 id 字段）。"""
    digest = hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:12]
    return f"claim-{digest}"


def find_claim(profile: Profile, claim_id: str) -> NarrativeClaim | None:
    """按 claim_id 在 profile.narrative_claims 里定位主张（文本哈希匹配）。"""
    for claim in profile.narrative_claims:
        if claim_id_for(claim.text) == claim_id:
            return claim
    return None


def to_claim_card(claim: NarrativeClaim) -> dict[str, Any]:
    """NarrativeClaim → ClaimCard 契约（spec §1）；来源补 at 空串（无观察时间记录）。"""
    sources = [{"kind": s.kind, "ref": s.ref, "at": ""} for s in claim.sources]
    return {
        "type": "claim",
        "claim_id": claim_id_for(claim.text),
        "text": claim.text,
        "state": claim.state,
        "evidence_count": claim.evidence_count,
        "sources": sources,
        "confidence": claim.confidence,
    }


def profile_contract(profile: Profile) -> dict[str, Any]:
    """Profile → 前端画像契约：M1 schema 直出，narrative_claims 换成 ClaimCard 形状。"""
    data = profile.model_dump()
    data["narrative_claims"] = [to_claim_card(c) for c in profile.narrative_claims]
    return data


def format_salary(salary: SalaryRange | None) -> str:
    """年薪 SalaryRange → 展示文本（万/年，两端缺失时返回空串）。"""
    if salary is None:
        return ""
    lo, hi = salary.min_annual, salary.max_annual
    if lo is None and hi is None:
        return ""

    def _wan(value: int) -> float:
        return value / 10000.0

    if lo is not None and hi is not None:
        return f"{_wan(lo):g}-{_wan(hi):g}万/年"
    if lo is not None:
        return f"≥{_wan(lo):g}万/年"
    if hi is not None:
        return f"≤{_wan(hi):g}万/年"
    return ""


def risk_hits(job: Job) -> list[dict[str, str]]:
    """复用 field.risks.assess 取结构风险命中（{key,label,why,severity}），容错非 list。"""
    hits = assess(job).get("hits")
    if not isinstance(hits, list):
        return []
    return [h for h in hits if isinstance(h, dict)]


def estimate_verdict(job: Job, deal_breakers: list[str]) -> str:
    """缺省判定估算（无 match 数据时）：deal-breaker 命中→skip、有结构风险→hold、否则 apply。

    deviation：generate_report 只落 jobs 表不落 verdict，这里用风险评估 + 硬边界
    模拟 decide() 的结构调制项；市场/成长契合未知按中性处理。
    """
    keys = {str(h.get("key", "")) for h in risk_hits(job)}
    if keys & set(deal_breakers):
        return "skip"
    if keys:
        return "hold"
    return "apply"


def estimate_reason(job: Job, verdict: str, hits: list[dict[str, str]]) -> str:
    """缺省估算的理由文案（无 decisions 缓存时）。"""
    labels = [str(h.get("label", "")) for h in hits if h.get("label")]
    if verdict == "skip":
        why = "命中" + "、".join(labels) if labels else "与画像中的硬边界冲突"
        return f"缺省估算：{why}，建议不投（可运行报告复核）。"
    if verdict == "hold":
        joined = "、".join(labels)
        return f"缺省估算：命中 {joined} 结构性风险，先观望（可运行报告复核）。"
    return "缺省估算：无已存匹配证据与明显风险，按中性契合建议投递（可运行报告复核）。"


def job_contract(
    job: Job,
    decisions: dict[str, dict[str, Any]],
    deal_breakers: list[str],
) -> dict[str, Any]:
    """Job + decisions 缓存 → spec §1 工作台列表契约。

    gap 从 decisions 缓存的 gaps 透传（matcher 产出，LLM 无 gaps → []）；
    remediation 暂无数据源，留空由前端隐藏；evidence 由 JD 摘要 + 缓存理由构成。
    """
    hits = risk_hits(job)
    cached = decisions.get(job.url)
    cached_verdict = str(cached["verdict"]) if cached and cached.get("verdict") else ""
    verdict = cached_verdict or estimate_verdict(job, deal_breakers)
    cached_reason = str(cached["reason"]) if cached and cached.get("reason") else ""
    reason = cached_reason or estimate_reason(job, verdict, hits)
    cached_gaps = cached.get("gaps") if cached else None

    evidence: list[dict[str, str]] = []
    snippet = (job.description or "").strip()
    if snippet:
        evidence.append({"kind": "jd", "ref": job.url, "text": snippet[:200]})
    if cached and cached.get("reason"):
        evidence.append({"kind": "system", "ref": "coarse-match", "text": str(cached["reason"])})

    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": format_salary(job.salary),
        "url": job.url,
        "verdict": verdict,
        "reason": reason,
        "risk_hits": [
            {
                "key": str(h.get("key", "")),
                "label": str(h.get("label", "")),
                "why": str(h.get("why", "")),
            }
            for h in hits
        ],
        "gap": [g for g in cached_gaps if isinstance(g, dict)]
        if isinstance(cached_gaps, list)
        else [],
        "remediation": [],
        "evidence": evidence,
    }
