"""M4 反馈回流管线（spec §1.3/§1.4）：显示性偏好规则回流 + 叙事修正接线。

规则版无 LLM——LLM 不改偏好（D18 人机边界同源）；偏好只动 ordering 与 evidence，
绝不改 narrative 文本。叙事修正复用 DefaultProfileEngine.update_from_feedback 的
claim 证据累积语义（note 前8/后8字符命中 trial claim → evidence_count+1），
以模块内纯函数移植，不实例化 engine（避免 LLM 依赖）。
"""

from __future__ import annotations

import re

from talentforge.domain.decision import Verdict
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.job import Job
from talentforge.domain.profile import ClaimSource, OrdinalPreference, Profile

SALARY_ATTRIBUTE = "薪资"  # 词表规范词（profile/vocab.ATTRIBUTE_VOCAB）
POSITIVE_OUTCOMES = ("offer", "interview")  # 确认升位的正向结果

_NOTE_TRUNCATE = 40
_CLAIM_KEY_SPAN = 8

_OPEN_TIER_RE = re.compile(r"(\d+(?:\.\d+)?)万以上")
_RANGE_TIER_RE = re.compile(r"(\d+(?:\.\d+)?)万?\s*-\s*(\d+(?:\.\d+)?)万")


def _tier_bounds(item: str) -> tuple[float, float | None] | None:
    """ordering 项 → 万区间："30-40万"→(30, 40)，"40万以上"→(40, None)；无数字 → None。"""
    if m := _OPEN_TIER_RE.search(item):
        return float(m.group(1)), None
    if m := _RANGE_TIER_RE.search(item):
        return float(m.group(1)), float(m.group(2))
    return None


def _salary_tier(job: Job, ordering: list[str]) -> str | None:
    """岗位薪资（max_annual 换算万，如 500000→50万）→ salary ordering 中命中区间的段位 key。

    闭区间匹配（"40万以上"为 ≥ 开区间）；区间边界重叠时取 ordering 中靠前者；
    无薪资或未命中任何段位返回 None（跳过段位操作，只做叙事修正）。
    """
    if job.salary is None or job.salary.max_annual is None:
        return None
    wan = job.salary.max_annual / 10000.0
    for item in ordering:
        bounds = _tier_bounds(item)
        if bounds is None:
            continue
        lo, hi = bounds
        if wan >= lo and (hi is None or wan <= hi):
            return item
    return None


def _salary_text(job: Job) -> str:
    """SalaryRange → evidence 用薪资文本（万/年，同 api.common.format_salary 语义）。"""
    salary = job.salary
    if salary is None:
        return ""

    def wan(value: int) -> str:
        return f"{value / 10000.0:g}"

    if salary.min_annual is not None and salary.max_annual is not None:
        return f"{wan(salary.min_annual)}-{wan(salary.max_annual)}万/年"
    if salary.max_annual is not None:
        return f"≤{wan(salary.max_annual)}万/年"
    if salary.min_annual is not None:
        return f"≥{wan(salary.min_annual)}万/年"
    return ""


def _revise_narrative(profile: Profile, event: FeedbackEvent) -> list[str]:
    """叙事修正（spec §1.4）：note 前8/后8字符命中 trial claim → evidence_count+1。

    语义与 DefaultProfileEngine.update_from_feedback 一致；直接操作传入的
    （已深拷贝的）profile，返回变更摘要。
    """
    note = f"{event.dialogue_note} {event.outcome or ''}"
    changes: list[str] = []
    for claim in profile.narrative_claims:
        if claim.state != "trial" or not claim.text:
            continue
        keys = {claim.text[:_CLAIM_KEY_SPAN], claim.text[-_CLAIM_KEY_SPAN:]}
        if any(k and k in note for k in keys):
            claim.evidence_count += 1
            claim.sources.append(ClaimSource(kind="feedback", ref=event.job_id))
            changes.append(f"叙事主张证据 +1: {claim.text[:24]}")
    return changes


def _salary_feedback(pref: OrdinalPreference, event: FeedbackEvent, job: Job) -> list[str]:
    """偏好回流规则表（spec §1.3）作用于薪资偏好，返回变更摘要。

    - decided：不动 ordering，只在命中段位 evidence 记"已在此段位行动"
      （skip 带理由 → 截断 40 字注释文案）；
    - outcome 且 offer/interview：段位 +1 位（向更优方向；已在最前不动）+ evidence 记录；
    - 单次调用每个 ordering 最多一次位置变动（防抖）。
    """
    tier = _salary_tier(job, pref.ordering)
    if tier is None:
        return []
    date = event.at.strftime("%Y-%m-%d")
    title = event.job_title or job.title
    changes: list[str] = []
    match event.action:
        case "outcome":
            if event.outcome in POSITIVE_OUTCOMES:
                idx = pref.ordering.index(tier)
                if idx > 0:
                    pref.ordering[idx - 1], pref.ordering[idx] = (
                        pref.ordering[idx], pref.ordering[idx - 1],
                    )
                    changes.append(f"salary ordering: '{tier}' +1 位（{event.outcome}）")
                record = f"{date} {event.outcome} {title}({_salary_text(job)})"
                pref.evidence.append(record)
                changes.append(f"evidence +1: {record}")
        case "decided":
            if event.decision_verdict == Verdict.SKIP and event.dialogue_note:
                record = f"{date} skip {title}: {event.dialogue_note[:_NOTE_TRUNCATE]}"
            else:
                record = f"{date} {event.decision_verdict.value} {title}({_salary_text(job)})"
            pref.evidence.append(record)
            changes.append(f"evidence +1: {record}")
    return changes


class FeedbackPipeline:
    """回流管线：单个 FeedbackEvent → (新 Profile, 人类可读变更摘要)。纯函数式不改入参。"""

    def apply(
        self, profile: Profile, event: FeedbackEvent, job: Job | None = None
    ) -> tuple[Profile, list[str]]:
        """深拷贝 profile 后回流：薪资段位规则 + 叙事修正；返回 (新 profile, 变更列表)。

        job 为 None 或薪资段位未命中时跳过段位操作只做叙事修正；无变更返回空列表。
        """
        new_profile = profile.model_copy(deep=True)
        salary_pref = new_profile.utility_preferences.get(SALARY_ATTRIBUTE)
        changes: list[str] = []
        if job is not None and salary_pref is not None:
            changes.extend(_salary_feedback(salary_pref, event, job))
        changes.extend(_revise_narrative(new_profile, event))
        return new_profile, changes
