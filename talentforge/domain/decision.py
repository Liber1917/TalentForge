from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    APPLY = "apply"  # 投
    HOLD = "hold"  # 观望
    SKIP = "skip"  # 不投


class ExplainableLink(BaseModel):
    """可解释链一环：画像证据 × 胜任力维度 × JD 原文。"""

    dimension: str
    profile_evidence: str
    jd_text: str
    assessment: str  # 匹配 | 差距 | 缺失


class Decision(BaseModel):
    """三元决策 + 可解释链 + 差距/补短板 + 结构性追问。"""

    job_id: str
    verdict: Verdict
    reason: str = ""
    explainable_chain: list[ExplainableLink] = Field(default_factory=list)
    gap: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)
    structural_reflection: list[str] = Field(default_factory=list)
    reflective_question: str | None = None  # 反思性对话钩子（D11）