import pytest
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.decision import Verdict
from talentforge.profile.engine import DefaultProfileEngine, RESUME_BOOTSTRAP_SYSTEM_PROMPT

CANNED = """
{"identity": "后端基础设施倾向", "values": ["工程美学"], "deep_drives": ["把齿轮咬合讲清楚"],
 "cognitive_style": "原理型", "claims": [{"text": "偏好后端基础设施方向", "confidence": 0.7}]}
"""

class FakeLLM:
    async def chat(self, system: str, user: str) -> str:
        FakeLLM.seen = (system, user)
        return "```json\n" + CANNED + "\n```"

@pytest.mark.asyncio
async def test_build_profile_resume_bootstrap():
    eng = DefaultProfileEngine(llm=FakeLLM())
    p = await eng.build_profile({
        "name": "张三", "skills": ["Python"],
        "resume_text": "做过分布式存储课程项目…",
        "structural": {"cash_buffer": "约6个月",
                       "exploitation_redlines": [{"kind": "竞业限制", "stance": "never"}]},
        "utility_raw": [{"attribute": "薪资", "ordering": ["30k", "25k", "20k"]},
                        {"attribute": "想要摸真东西", "ordering": []}],
    })
    assert p.name == "张三"
    assert p.narrative.identity == "后端基础设施倾向"
    assert p.narrative_claims[0].state == "trial"
    assert p.narrative_claims[0].sources[0].kind == "resume"
    assert p.utility_preferences["薪资"].ordering[0] == "30k"
    assert p.utility_preferences["其他"].ordering == []          # OOV 归一
    assert "竞业限制" in p.deal_breakers                           # never→硬否决同步
    sysmsg, usermsg = FakeLLM.seen
    assert sysmsg == RESUME_BOOTSTRAP_SYSTEM_PROMPT and "分布式存储" in usermsg

@pytest.mark.asyncio
async def test_update_from_feedback_accumulates_evidence():
    eng = DefaultProfileEngine(llm=FakeLLM())
    p = await eng.build_profile({"name": "张三", "resume_text": "x"})
    ev = FeedbackEvent(job_id="j", decision_verdict=Verdict.APPLY,
                       dialogue_note="我确实更想做后端基础设施方向的工作")
    p2 = await eng.update_from_feedback(p, ev)
    assert p2.narrative_claims[0].evidence_count == 1
    assert p2.narrative_claims[0].sources[-1].kind == "feedback"
