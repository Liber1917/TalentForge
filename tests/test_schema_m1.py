from talentforge.domain.profile import (
    NarrativeClaim, ClaimSource, StructuralPosition, Profile,
    ExploitationRedline, ReproductionCosts, MobilityStatus, SupportRelation,
)

def test_narrative_claim_defaults():
    c = NarrativeClaim(text="偏好后端基础设施方向")
    assert c.state == "trial" and c.evidence_count == 0 and c.sources == []

def test_eight_grid_fields_present():
    sp = StructuralPosition(
        cash_buffer="约6个月",
        stage="在读·大三",
        support_network=[SupportRelation(kind="学长", note="可内推")],
        exploitation_redlines=[ExploitationRedline(kind="竞业限制", stance="never")],
        reproduction_costs=ReproductionCosts(housing="学校宿舍", skill_half_life_years=2.0),
        mobility=MobilityStatus(dare_bare_quit=False),
        reservation_wage=None,
    )
    assert sp.cash_buffer == "约6个月"
    assert sp.exploitation_redlines[0].stance == "never"

def test_backward_compat_profile_without_new_fields():
    p = Profile(name="张三")  # 不传 narrative_claims
    assert p.narrative_claims == []
    old = p.model_dump(); old.pop("narrative_claims")
    assert Profile.model_validate(old).name == "张三"  # 旧数据可加载
