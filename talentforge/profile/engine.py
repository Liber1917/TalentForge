"""简历 bootstrap + 隐式证据累积（O1/D16：显式优先、α 两态、对话即蒸馏）。"""
from __future__ import annotations

from typing import Any

from talentforge.domain.profile import (
    ClaimSource, NarrativeClaim, OrdinalPreference, Profile, SalaryRange, StructuralPosition,
)
from talentforge.domain.feedback import FeedbackEvent
from talentforge.llm.client import LLMClient
from talentforge.llm.json_utils import extract_json
from talentforge.profile.vocab import resolve_attribute

RESUME_BOOTSTRAP_SYSTEM_PROMPT = (
    "你是求职者画像构建器。根据用户消息中的简历文本，推断其人格叙事。"
    "只输出一个 JSON 对象，不要输出其他文字。格式："
    '{"identity": str, "values": [str], "deep_drives": [str], "cognitive_style": str,'
    ' "claims": [{"text": str, "confidence": float}]}。'
    "claims 是从简历可回溯的具体叙事主张（每条对应简历中的真实内容），不超过 8 条。"
)

_STRUCTURAL_KEYS = {
    "cash_buffer", "stage", "city_constraints", "family_duty", "economic_independence",
    "family_payback", "market_assessment",
}
_REDLINE_KEYS = {"kind", "stance"}


class DefaultProfileEngine:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def build_profile(self, explicit: dict[str, Any]) -> Profile:
        structural_raw = dict(explicit.get("structural") or {})
        redlines = [
            {"kind": r.get("kind", ""), "stance": r.get("stance", "negotiable")}
            for r in structural_raw.pop("exploitation_redlines", [])
        ]
        structural_raw["exploitation_redlines"] = redlines
        sp = StructuralPosition.model_validate(structural_raw)
        reservation = explicit.get("reservation_wage")
        if isinstance(reservation, dict):
            sp.reservation_wage = SalaryRange.model_validate(reservation)

        raw = await self._llm.chat(
            RESUME_BOOTSTRAP_SYSTEM_PROMPT,
            f"简历文本：\n{str(explicit.get('resume_text', ''))[:4000]}",
        )
        data = extract_json(raw)

        claims = [
            NarrativeClaim(
                text=str(c.get("text", "")).strip(),
                confidence=float(c.get("confidence", 0.5)),
                sources=[ClaimSource(kind="resume", ref="bootstrap")],
            )
            for c in data.get("claims", []) if str(c.get("text", "")).strip()
        ][:8]

        utility: dict[str, OrdinalPreference] = {}
        for item in explicit.get("utility_raw", []):
            attr = resolve_attribute(str(item.get("attribute", "")))
            utility[attr] = OrdinalPreference(
                attribute=attr, ordering=[str(x) for x in item.get("ordering", [])]
            )

        deal_breakers = [r["kind"] for r in redlines if r["stance"] == "never"]

        return Profile(
            name=str(explicit.get("name", "")),
            email=explicit.get("email"),
            years_experience=float(explicit.get("years_experience", 0.0)),
            skills=[str(s) for s in explicit.get("skills", [])],
            desired_roles=[str(r) for r in explicit.get("desired_roles", [])],
            preferred_locations=[str(x) for x in explicit.get("preferred_locations", [])],
            deal_breakers=deal_breakers,
            narrative={
                "identity": str(data.get("identity", "")),
                "values": [str(v) for v in data.get("values", [])],
                "deep_drives": [str(d) for d in data.get("deep_drives", [])],
                "cognitive_style": str(data.get("cognitive_style", "")) or None,
            },
            utility_preferences=utility,
            structural_position=sp,
            narrative_claims=claims,
        )

    async def update_from_feedback(self, profile: Profile, event: FeedbackEvent) -> Profile:
        note = f"{event.dialogue_note} {event.outcome or ''}"
        changed = False
        for claim in profile.narrative_claims:
            if claim.state != "trial" or not claim.text:
                continue
            keys = {claim.text[:8], claim.text[-8:]}
            if any(k and k in note for k in keys):
                claim.evidence_count += 1
                claim.sources.append(ClaimSource(kind="feedback", ref=event.job_id))
                changed = True
        return profile if changed else profile.model_copy(deep=True)
