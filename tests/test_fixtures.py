"""M3 fixture 测试：卡片判别联合可解析、四类型全覆盖、岗位三态、画像 trial/active+八格。"""

from __future__ import annotations

from pydantic import TypeAdapter

from talentforge.api.fixtures import get_fixture_chat, get_fixture_jobs, get_fixture_profile
from talentforge.api.schemas import (
    CardUnion,
    ChatTurn,
    ClaimCard,
    DecisionCard,
    ReflectivePrompt,
    RiskNote,
)

_Card = DecisionCard | ClaimCard | RiskNote | ReflectivePrompt

_CARD_MODELS: dict[str, type[_Card]] = {
    "decision": DecisionCard,
    "claim": ClaimCard,
    "risk": RiskNote,
    "reflective": ReflectivePrompt,
}


def _all_cards() -> list[_Card]:
    turns = get_fixture_chat()
    assert all(isinstance(t, ChatTurn) for t in turns)
    return [card for turn in turns for card in turn.cards]


def test_fixture_chat_has_five_turns() -> None:
    assert len(get_fixture_chat()) == 5


def test_fixture_cards_parse_via_card_union_discriminator() -> None:
    adapter: TypeAdapter[CardUnion] = TypeAdapter(CardUnion)
    for card in _all_cards():
        parsed = adapter.validate_python(card.model_dump())
        expected = _CARD_MODELS[card.type]
        assert type(parsed) is expected
        assert parsed.type == card.type


def test_fixture_chat_covers_all_four_card_types() -> None:
    types = [card.type for card in _all_cards()]
    assert set(types) == {"decision", "claim", "risk", "reflective"}
    assert types.count("decision") == 2
    assert types.count("claim") == 1
    assert types.count("risk") == 1
    assert types.count("reflective") == 1


def test_fixture_jobs_cover_apply_hold_skip_and_risk_presence() -> None:
    jobs = get_fixture_jobs()
    assert len(jobs) == 8
    verdicts = {job["verdict"] for job in jobs}
    assert verdicts == {"apply", "hold", "skip"}
    has_risk = any(job["risk_hits"] for job in jobs)
    no_risk = any(not job["risk_hits"] for job in jobs)
    assert has_risk and no_risk
    required = {
        "title", "company", "location", "salary", "url",
        "verdict", "reason", "risk_hits", "gap", "remediation",
    }
    for job in jobs:
        assert required <= set(job)


def test_fixture_profile_has_trial_and_active_claims() -> None:
    profile = get_fixture_profile()
    claims = profile["narrative_claims"]
    states = {c["state"] for c in claims}
    assert "trial" in states
    assert "active" in states
    assert sum(1 for c in claims if c["state"] == "trial") == 3


def test_fixture_profile_has_complete_three_tracks() -> None:
    profile = get_fixture_profile()
    narrative = profile["narrative"]
    assert narrative["identity"]
    assert narrative["values"]
    assert profile["utility_preferences"]
    sp = profile["structural_position"]
    octet_keys = (
        "cash_buffer", "stage", "city_constraints", "family_duty", "support_network",
        "economic_independence", "family_payback", "reservation_wage",
    )
    for key in octet_keys:
        assert key in sp
    assert sp["cash_buffer"]
    assert sp["reservation_wage"]["min_annual"] >= 0
