from __future__ import annotations

from pydantic import BaseModel, Field


class CompetencyDimension(BaseModel):
    """胜任力维度（一级）：抽象特质，非技能（TalentModel-skill 约束）。"""

    key: str  # D1..D6
    name: str  # 认知复杂度 / 内驱与主动闭环 / ...
    definition: str
    behaviors: list[str] = Field(default_factory=list)  # 二级：可观察行为
    evidence: list[str] = Field(default_factory=list)  # 三级：证据


class CompetencyModel(BaseModel):
    """岗位胜任力框架（结构化 JSON，非仅 HTML，O2 前置）。"""

    role: str
    level: str  # 校招 | 实习 | 应届 | 社招
    dimensions: list[CompetencyDimension] = Field(default_factory=list)  # 6 个
    candidate_evidence: dict[str, list[str]] = Field(default_factory=dict)  # dimension_key -> evidence