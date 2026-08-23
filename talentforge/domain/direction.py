"""方向域模型（M7 spec §2）：DirectionCard —— 三口径方向卡。

EvidenceRef 与 api/schemas.py 同形状但域内自建（域模型不依赖 api 层，
同 ClaimSource/ClaimCard 分立先例）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    """证据链一环：来源种类 + 锚点引用 + 原文摘录。"""

    kind: str  # work | profile | behavior | dialogue
    ref: str = ""
    text: str = ""


class DirectionCard(BaseModel):
    """方向卡（spec §2）：三口径 + 证据链 + 市场验证 + 约束碰撞。

    card_id 由标题哈希稳定导出（dir-{sha1[:12]}，同 claim_id_for 模式）；
    created_from 非空 = 深谈修正卡（快照替换时不被冲掉，溯源快照 id）。
    """

    card_id: str
    scope: Literal["track", "lifestyle", "field"]  # 赛道/活法/场域
    title: str
    why_you: list[EvidenceRef] = Field(default_factory=list)
    market_evidence: str = ""
    data_backed: bool = False
    distance: str = ""
    first_step: str = ""
    constraint_check: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    created_from: str = ""
