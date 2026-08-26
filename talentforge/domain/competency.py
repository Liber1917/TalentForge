"""岗位胜任力模型（继承 TalentModel-skill 内核，M9）。

三层结构（TalentModel 铁律）：
  一级 CompetencyDimension.name —— 人的稳定特质（方向感、认知复杂度、韧性…），
      禁止技能/工具/技术栈（Python/Go 降级到二级行为或三级证据）；
  二级 behaviors —— 可观察行为，技能和岗位任务的落脚点；
  三级（证据）—— 画像 claims/作品等证据引用，挂在 DimensionAssessment。

岗位侧建模（用户决策）：画像维度不动，每个岗位/同类岗位簇建一个胜任力模型，
匹配时拿画像证据逐维对齐 → DimensionAssessment（strong/partial/missing）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CompetencyDimension(BaseModel):
    """胜任力一级维度 + 二级行为（岗位模型的一层）。"""

    key: str = ""  # 维度编号（D1-D6，builder 输出；匹配对齐路径可留空）
    name: str
    behaviors: list[str] = Field(default_factory=list)


class CompetencyModel(BaseModel):
    """单个岗位（或同类岗位簇）的胜任力模型。

    role 是展示用岗位名；role_key 是聚类簇标识（title 归一化 + 技能重叠），
    同类岗位复用同一模型；level 为招聘级别（校招/社招，TalentModel 边界约束）；
    source 记录模型提炼自哪些信号（JD + 市场校准），供展示与审计。
    """

    role: str = ""
    role_key: str = ""
    level: str = ""
    dimensions: list[CompetencyDimension] = Field(default_factory=list)
    source: str = ""
    clusterer_version: str = "rule-v1"


class DimensionAssessment(BaseModel):
    """逐维对齐结果：岗位维度 × 画像证据强度。"""

    dimension: str
    # strong=画像证据充分 / partial=部分证据 / missing=无证据
    candidate_level: Literal["strong", "partial", "missing"] = "missing"
    # 画像证据引用（claims 文本 / 作品名），空 = 缺失
    evidence_refs: list[str] = Field(default_factory=list)
    # JD 要求 vs 画像现状的缺口说明（missing/partial 时必有）
    gap_note: str = ""


class CompetencyCluster(BaseModel):
    """聚类簇：共享一个胜任力模型的同类岗位集合。"""

    cluster_id: str
    role_key: str
    member_job_ids: list[str] = Field(default_factory=list)
    model: CompetencyModel | None = None
