from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FitLevel(str, Enum):
    """序数契合等级（O2 量化方法待定，MVP 用高/低占位）。"""

    HIGH = "high"
    LOW = "low"


class StructuralAssessment(BaseModel):
    """结构认知（第三维，作为调制项，§6.1）。"""

    risks: list[str] = Field(default_factory=list)  # 命中的 risk key
    notes: list[str] = Field(default_factory=list)  # 政治经济学警示


class Match(BaseModel):
    """三维匹配结果（市场契合 × 成长契合 × 结构认知）。"""

    job_id: str
    market_fit: FitLevel | None = None
    growth_fit: FitLevel | None = None
    structural: StructuralAssessment = Field(default_factory=StructuralAssessment)
    reasoning: list[str] = Field(default_factory=list)
    matched_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)