"""粗匹配器：LLM 单跳把候选人画像与岗位压成 市场契合×成长契合（FitLevel）。

prompt-cache 约定（见 llm/client.py 模块 docstring）：system 必须是模块级静态
常量，一切变量放 user message。本模块 system 即 COARSE_MATCH_SYSTEM_PROMPT，
match() 只负责按 稳定→可变 排序拼接 user 与解析输出，绝不改写 system。
"""
from __future__ import annotations

from talentforge.domain.job import Job
from talentforge.domain.match import FitLevel, Match, StructuralAssessment
from talentforge.domain.profile import Profile
from talentforge.llm.client import LLMClient
from talentforge.llm.json_utils import extract_json

# 静态 system：角色定义 + 输出 schema，无任何变量（prompt-cache 合规）。
COARSE_MATCH_SYSTEM_PROMPT = (
    "你是求职匹配评估器。根据候选人画像与岗位信息，评估两个维度的契合度，"
    "并输出 JSON。\n\n"
    "评估标准：\n"
    "- market_fit（市场契合）：候选人已验证技能与岗位要求的匹配程度；"
    "标 [待验证] 的主张仅作参考。\n"
    "- growth_fit（成长契合）：岗位方向是否推进候选人成长或深层驱动。\n"
    "- gaps（落差提取）：JD 明确要求而画像缺失/未验证的技能；最多 3 条，"
    "按 severity 从重到轻排序；evidence 必须同时引用 JD 要求与画像现状的落差；"
    "无明确落差时不输出该字段。\n\n"
    "只输出 JSON，不要任何其他文字：\n"
    '{"market_fit": "high|low", "growth_fit": "high|low", '
    '"reasoning": [理由列表], "matched": [契合维度列表], '
    '"missing": [缺失维度列表], '
    '"gaps": [{"skill": "技能名", "severity": "major|minor", '
    '"evidence": "JD 要求与画像现状的落差依据"}]}'
)

_CLAIM_STATES = ("active", "trial")
_MAX_CLAIMS = 20
_MAX_DESCRIPTION_CHARS = 1500
_MAX_GAPS = 3
_MAX_GAP_SKILL_CHARS = 40
_MAX_GAP_EVIDENCE_CHARS = 120
_GAP_SEVERITIES = ("major", "minor")


def _risk_hits(field_notes: dict[str, object]) -> list[dict[str, str]]:
    """从 field_notes 提取命中风险条目（{key,label,why,severity}），容错非 list/非 dict。"""
    hits = field_notes.get("hits")
    if not isinstance(hits, list):
        return []
    return [h for h in hits if isinstance(h, dict)]


def _format_claims(profile: Profile) -> list[str]:
    """叙事主张摘要：active→[已验证]，trial→[待验证]，最多取前 20 条。"""
    lines: list[str] = []
    claims = [c for c in profile.narrative_claims if c.state in _CLAIM_STATES][:_MAX_CLAIMS]
    if not claims:
        return lines
    lines.append("叙事主张（文本 + 验证状态）：")
    for claim in claims:
        mark = "[已验证]" if claim.state == "active" else "[待验证]"
        lines.append(f"- {mark} {claim.text}")
    return lines


def _format_salary(job: Job) -> str:
    """年薪口径文本；两端任一缺失时降级为单边/空。"""
    salary = job.salary
    if salary is None:
        return ""
    lo, hi = salary.min_annual, salary.max_annual
    if lo is None and hi is None:
        return ""
    if lo is None:
        return f"年薪 ≤{hi} {salary.currency}"
    if hi is None:
        return f"年薪 ≥{lo} {salary.currency}"
    return f"年薪 {lo}-{hi} {salary.currency}"


def _build_user_message(profile: Profile, job: Job, field_notes: dict[str, object]) -> str:
    """按 稳定→可变 排序构造 user message：Profile → Job → field_notes。"""
    lines: list[str] = ["【候选人画像】"]
    lines.append(f"姓名：{profile.name}")
    lines.append(f"经验年限：{profile.years_experience} 年")
    skills = "、".join(profile.skills) if profile.skills else "未提供"
    lines.append(f"技能：{skills}")
    lines.extend(_format_claims(profile))

    lines.append("")
    lines.append("【岗位信息】")
    lines.append(f"职位：{job.title}")
    lines.append(f"公司：{job.company}")
    if job.description:
        lines.append(f"描述：{job.description[:_MAX_DESCRIPTION_CHARS]}")
    if job.tags:
        lines.append(f"标签：{'、'.join(job.tags)}")
    salary = _format_salary(job)
    if salary:
        lines.append(f"薪资：{salary}")

    lines.append("")
    lines.append("【场域风险提示】")
    hits = _risk_hits(field_notes)
    if hits:
        for hit in hits:
            key = str(hit.get("key", "未知"))
            label = str(hit.get("label", ""))
            lines.append(f"- {key}（{label}）")
    else:
        lines.append("无命中")

    return "\n".join(lines)


def _parse_fit(value: object) -> FitLevel:
    """LLM 输出 fit 字符串转 FitLevel；非法/缺失一律默认 LOW。"""
    if isinstance(value, str):
        try:
            return FitLevel(value)
        except ValueError:
            return FitLevel.LOW
    return FitLevel.LOW


def _as_strings(value: object) -> list[str]:
    """reasoning/matched/missing 兜底为 list[str]；非 list 返回空。"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _parse_gaps(value: object) -> list[dict[str, str]]:
    """LLM 输出 gaps 容错解析为 [{skill, severity, evidence}]。

    非 list 或 entry 非 dict 跳过；skill/evidence str 化并截断（40/120 字）；
    severity 只认 major/minor，其余（含缺失）归 minor；最多取前 3 条。
    LLM 未输出 gaps 字段时解析为空列表（旧响应兼容）。
    """
    if not isinstance(value, list):
        return []
    gaps: list[dict[str, str]] = []
    for item in value[:_MAX_GAPS]:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "").strip().lower()
        gaps.append(
            {
                "skill": str(item.get("skill") or "")[:_MAX_GAP_SKILL_CHARS],
                "severity": severity if severity in _GAP_SEVERITIES else "minor",
                "evidence": str(item.get("evidence") or "")[:_MAX_GAP_EVIDENCE_CHARS],
            }
        )
    return gaps


class CoarseMatcher:
    """粗匹配器：一次 LLM 调用产出市场/成长两维 FitLevel（单跳，不回溯）。"""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def match(
        self, profile: Profile, job: Job, field_notes: dict[str, object]
    ) -> Match:
        user = _build_user_message(profile, job, field_notes)
        raw = await self._llm.chat(COARSE_MATCH_SYSTEM_PROMPT, user)
        try:
            data = extract_json(raw)
        except ValueError as exc:
            return Match(
                job_id=job.id,
                market_fit=FitLevel.LOW,
                growth_fit=FitLevel.LOW,
                reasoning=[f"匹配评估失败: {exc}"],
            )
        hits = _risk_hits(field_notes)
        return Match(
            job_id=job.id,
            market_fit=_parse_fit(data.get("market_fit")),
            growth_fit=_parse_fit(data.get("growth_fit")),
            structural=StructuralAssessment(risks=[h["key"] for h in hits]),
            reasoning=_as_strings(data.get("reasoning")),
            matched_dimensions=_as_strings(data.get("matched")),
            missing_dimensions=_as_strings(data.get("missing")),
            gaps=_parse_gaps(data.get("gaps")),
        )
