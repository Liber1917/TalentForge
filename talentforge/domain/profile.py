from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class SalaryRange(BaseModel):
    min_annual: int | None = Field(default=None, ge=0)
    max_annual: int | None = Field(default=None, ge=0)
    currency: str = "CNY"


class NarrativeIdentity(BaseModel):
    """人格叙事轨：自然语言为主，结构化字段待研究扩展。"""

    identity: str = ""
    values: list[str] = Field(default_factory=list)
    deep_drives: list[str] = Field(default_factory=list)
    cognitive_style: str | None = None


class ClaimSource(BaseModel):
    """证据来源：简历段落/对话轮次/反馈事件/行为。"""
    kind: Literal["resume", "dialogue", "feedback", "behavior", "system"]
    ref: str = ""

class NarrativeClaim(BaseModel):
    """α 假设机制（O1/D16）：叙事主张，trial→（M3 用户确认）→active；archived 为归档。"""
    text: str
    state: Literal["trial", "active", "archived"] = "trial"
    evidence_count: int = 0
    confidence: float = 0.5
    sources: list[ClaimSource] = Field(default_factory=list)

class SupportRelation(BaseModel):
    kind: str = ""   # 导师/学长/家庭/内推人/朋友
    note: str = ""

class ExploitationRedline(BaseModel):
    kind: str = ""   # 996/大小周/on_call/无偿加班/竞业限制/培训违约金/加班费模糊
    stance: Literal["accept", "negotiable", "never"] = "negotiable"

class ReproductionCosts(BaseModel):
    housing: str = ""
    commute: str = ""
    food: str = ""
    skill_half_life_years: float | None = None

class MobilityStatus(BaseModel):
    dare_bare_quit: bool = False
    note: str = ""


class StructuralPosition(BaseModel):
    """结构位置（D12）：研究阶段，自然语言 + 可扩展。"""

    material_conditions: str = ""
    social_relations: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    # —— 八格（O1 R3 / D17）：用户直填侧；市场侧(M2)入 market_assessment ——
    cash_buffer: Literal["≤3个月", "约6个月", "约1年", "≥2年"] | None = None
    stage: str = ""
    city_constraints: list[str] = Field(default_factory=list)
    family_duty: str = ""
    support_network: list[SupportRelation] = Field(default_factory=list)
    economic_independence: str = ""
    family_payback: bool = False
    reservation_wage: SalaryRange | None = None
    market_assessment: dict[str, Any] = Field(default_factory=dict)  # 系统估（M2，带证据标注）
    exploitation_redlines: list[ExploitationRedline] = Field(default_factory=list)
    reproduction_costs: ReproductionCosts | None = None
    mobility: MobilityStatus | None = None


class RevealedChoice(BaseModel):
    """显示性偏好（D6/O2）：投/拒/接offer 行为流。"""

    job_id: str
    choice: str  # applied | rejected | passed | offer_accepted | offer_rejected
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""


class OrdinalPreference(BaseModel):
    """岗位属性偏好序（序数，非基数）。"""

    attribute: str  # salary | tech_stack | work_mode | growth | stability | location | company_type
    ordering: list[str] = Field(default_factory=list)  # 偏好从高到低
    # 回流依据（M4），如 "2026-08-22 hold 星辰科技(25-50K·16薪)"
    evidence: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    """求职者画像：显式层 + 双轨 + 结构位置。"""

    name: str
    email: str | None = None
    years_experience: float = 0.0
    skills: list[str] = Field(default_factory=list)
    desired_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    salary_expectation: SalaryRange | None = None
    deal_breakers: list[str] = Field(default_factory=list)
    narrative: NarrativeIdentity = Field(default_factory=NarrativeIdentity)
    utility_preferences: dict[str, OrdinalPreference] = Field(default_factory=dict)
    structural_position: StructuralPosition = Field(default_factory=StructuralPosition)
    revealed_preferences: list[RevealedChoice] = Field(default_factory=list)
    narrative_claims: list[NarrativeClaim] = Field(default_factory=list)