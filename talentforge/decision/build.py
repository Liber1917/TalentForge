"""Decision 组装（D15 核心）：M9 调制回归 + 决策单一事实源。

曾被架构评审认定的漂移：missing≥2→hold 调制与决策 dict 手拼散落在
report/generate.py 编排层（绕过 D15 锁定的 decision 核心）——本模块把
两者收回核心，报告 items / decisions 落库 / 导出回测统一从 Decision 序列化。
"""

from __future__ import annotations

from pydantic import BaseModel

from talentforge.decision.verdict import Verdict, decide
from talentforge.domain.decision import Decision, ExplainableLink
from talentforge.domain.job import Job
from talentforge.domain.match import Match
from talentforge.domain.profile import Profile


def modulate(verdict: Verdict, match: Match) -> Verdict:
    """决策联动调制（M9）：岗位胜任力维度缺失 ≥2 → apply 降 hold。

    只降级不升级（非 apply 原样返回）；match 无 competency 数据时不触发。
    """
    missing = [a for a in match.competency if getattr(a, "candidate_level", None) == "missing"]
    if verdict is Verdict.APPLY and len(missing) >= 2:
        return Verdict.HOLD
    return verdict


def build_decision(
    job: Job,
    match: Match,
    risk_labels: list[str],
    profile: Profile,
    reflective_question: str | None = None,
) -> Decision:
    """组装核心 Decision：象限判定 + 结构调制 + M9 联动调制一次成型。

    可解释链逐维对应 competency 对齐结果（dimension/assessment/evidence_refs）；
    reflective_question 由编排层注入（规则模板，M3 换 LLM，不进核心）。
    """
    verdict = modulate(decide(match, profile.deal_breakers), match)
    chain = [
        ExplainableLink(
            dimension=str(getattr(a, "dimension", "")),
            profile_evidence="; ".join(getattr(a, "evidence_refs", []) or []),
            jd_text="",
            assessment=str(getattr(a, "candidate_level", "")),
        )
        for a in match.competency
    ]
    competency: list[dict[str, object]] = []
    for a in match.competency:
        if isinstance(a, BaseModel):
            competency.append(a.model_dump())
        elif isinstance(a, dict):
            competency.append(dict(a))
    return Decision(
        job_id=job.id,
        verdict=verdict,
        reason=match.reasoning[0] if match.reasoning else verdict.value,
        explainable_chain=chain,
        gap=match.gaps,
        competency=competency,
        risk_hits=risk_labels,
        reflective_question=reflective_question,
    )
