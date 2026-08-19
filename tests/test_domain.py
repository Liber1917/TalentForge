from talentforge.domain.profile import Profile, NarrativeIdentity, OrdinalPreference
from talentforge.domain.match import Match, FitLevel, StructuralAssessment
from talentforge.domain.decision import Decision, Verdict, ExplainableLink
from talentforge.domain.job import Job


def test_profile_defaults_and_dual_track():
    p = Profile(name="张三", skills=["Python"])
    assert p.narrative.identity == ""
    assert p.utility_preferences == {}
    assert p.revealed_preferences == []
    p.utility_preferences["work_mode"] = OrdinalPreference(
        attribute="work_mode", ordering=["remote", "hybrid", "onsite"]
    )
    assert p.utility_preferences["work_mode"].ordering[0] == "remote"


def test_match_fit_is_ordinal_enum():
    m = Match(job_id="j1", market_fit=FitLevel.HIGH, growth_fit=FitLevel.LOW)
    assert m.market_fit == FitLevel.HIGH
    assert m.structural.risks == []


def test_decision_explainable_chain_and_reflective_question():
    d = Decision(
        job_id="j1",
        verdict=Verdict.HOLD,
        explainable_chain=[
            ExplainableLink(
                dimension="D1",
                profile_evidence="简历有分布式项目",
                jd_text="要求高并发经验",
                assessment="部分匹配",
            )
        ],
        reflective_question="你连续三次都投了大小周岗位，优先级变了吗？",
    )
    assert d.reflective_question is not None
    assert len(d.explainable_chain) == 1


def test_job_has_structural_risk_keys():
    j = Job(source="boss", title="后端", company="X", location="深圳", url="https://x", risk_keys=["996"])
    assert "996" in j.risk_keys