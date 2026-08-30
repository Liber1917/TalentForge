"""D15 核心收编：M9 调制规则回归 decision 模块 + Decision 成为决策单一事实源。

曾被架构评审认定的漂移：missing≥2→hold 调制写在 report/generate.py 编排
闭包里（绕过 D15 锁定的 decision 核心），Decision 域模型死亡、报告手拼 dict。
"""

from __future__ import annotations

from pydantic import BaseModel

from talentforge.decision.build import build_decision, modulate
from talentforge.decision.verdict import Verdict
from talentforge.domain.decision import Decision
from talentforge.domain.job import Job
from talentforge.domain.match import FitLevel, Match
from talentforge.domain.profile import Profile


class _Align(BaseModel):
    dimension: str
    candidate_level: str = "partial"
    evidence_refs: list[str] = []


def _match(competency: list[_Align] | None = None, **overrides: object) -> Match:
    data: dict[str, object] = {
        "job_id": "j1",
        "market_fit": FitLevel.HIGH,
        "growth_fit": FitLevel.HIGH,
        "reasoning": ["市场与成长双契合"],
        "gaps": [{"skill": "Go", "severity": "major"}],
        "competency": competency if competency is not None else [
            _Align(dimension="工程实践", candidate_level="strong"),
        ],
    }
    data.update(overrides)
    return Match.model_validate(data)


def _job() -> Job:
    return Job(
        id="j1", title="Python 后端", company="A 公司", location="深圳", url="https://j1",
        source="boss", description="JD",
    )


def test_modulate_caps_apply_when_two_dimensions_missing() -> None:
    match = _match(competency=[
        _Align(dimension="工程实践", candidate_level="missing"),
        _Align(dimension="分布式", candidate_level="missing"),
    ])
    assert modulate(Verdict.APPLY, match) is Verdict.HOLD


def test_modulate_keeps_apply_when_fewer_than_two_missing() -> None:
    match = _match(competency=[
        _Align(dimension="工程实践", candidate_level="missing"),
        _Align(dimension="分布式", candidate_level="strong"),
    ])
    assert modulate(Verdict.APPLY, match) is Verdict.APPLY


def test_modulate_never_upgrades_non_apply() -> None:
    match = _match(competency=[
        _Align(dimension="a", candidate_level="missing"),
        _Align(dimension="b", candidate_level="missing"),
    ])
    assert modulate(Verdict.SKIP, match) is Verdict.SKIP
    assert modulate(Verdict.HOLD, match) is Verdict.HOLD


def test_build_decision_is_single_source_of_truth() -> None:
    match = _match(competency=[
        _Align(dimension="工程实践", candidate_level="missing", evidence_refs=["ref-1"]),
        _Align(dimension="分布式", candidate_level="missing"),
    ])
    decision = build_decision(
        _job(), match, risk_labels=["996 工作制"], profile=Profile(name="张三"),
        reflective_question="你怎么看？",
    )
    assert isinstance(decision, Decision)
    # M9 调制在核心内生效（2 个 missing → apply 降 hold）
    assert decision.verdict is Verdict.HOLD
    assert decision.reason == "市场与成长双契合"
    assert decision.gap == [{"skill": "Go", "severity": "major"}]
    assert decision.risk_hits == ["996 工作制"]
    assert decision.reflective_question == "你怎么看？"
    # competency 全量序列化 + 可解释链逐维对应
    assert [c["dimension"] for c in decision.competency] == ["工程实践", "分布式"]
    assert [link.dimension for link in decision.explainable_chain] == ["工程实践", "分布式"]
    assert all(link.assessment == "missing" for link in decision.explainable_chain)
    assert decision.explainable_chain[0].profile_evidence == "ref-1"


def test_build_decision_reason_falls_back_to_verdict() -> None:
    decision = build_decision(_job(), _match(reasoning=[]), [], Profile(name="张三"))
    assert decision.reason == decision.verdict.value
