from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StructuralRisk(BaseModel):
    """结构性风险信号（D12/D14）：每个带政治经济学解释。"""

    key: str  # 996 | 大小周 | 无社保 | 无偿加班 | 竞业限制 | ...
    label: str
    why: str  # 为什么这是剥削（政治经济学解释）
    severity: str = "warning"  # warning | deal_breaker


class FieldModel(BaseModel):
    """场域建模（劳动力市场政治经济学）。研究阶段，可扩展。"""

    industry: str = ""
    industry_analysis: str = ""
    risks: list[StructuralRisk] = Field(default_factory=list)
    ideology_signals: list[str] = Field(default_factory=list)  # 「996是福报」等
    extra: dict[str, Any] = Field(default_factory=dict)