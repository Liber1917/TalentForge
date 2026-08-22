"""Web 卡片 JSON 契约（spec-m3-web §1）：type 判别联合 + 对话轮次。

这些模型是前后端之间的数据契约——字段名/类型与 spec §1 完全一致。
前端只依赖这些字段渲染；后端（M3 Task 7 真端点）按此产出。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field


class JobRef(BaseModel):
    """决策卡引用的岗位摘要。"""

    title: str
    company: str
    url: str
    salary: str | None = None


class RiskHit(BaseModel):
    """决策卡命中的结构性风险：机器 key + 展示 label。"""

    key: str
    label: str


class EvidenceRef(BaseModel):
    """证据链一环：来源种类 + 锚点引用 + 原文摘录。"""

    kind: str  # resume | dialogue | feedback | behavior | jd | system
    ref: str
    text: str


class DecisionCard(BaseModel):
    """岗位决策卡：三元 verdict + 理由 + 风险命中 + 反思问题 + 证据链。"""

    type: Literal["decision"] = "decision"
    job: JobRef
    verdict: Literal["apply", "hold", "skip"]
    reason: str
    risk_hits: list[RiskHit] = Field(default_factory=list)
    reflective_question: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ClaimSourceRef(BaseModel):
    """主张卡证据来源：与 domain.ClaimSource 相同 kind/ref，另带观察时间 at。"""

    kind: str
    ref: str
    at: str = ""


class ClaimCard(BaseModel):
    """画像主张卡：α 假设的 trial→active→archived 状态 + 证据计数。"""

    type: Literal["claim"] = "claim"
    claim_id: str
    text: str
    state: Literal["trial", "active", "archived"] = "trial"
    evidence_count: int = 0
    sources: list[ClaimSourceRef] = Field(default_factory=list)
    confidence: float = 0.5


class RiskNote(BaseModel):
    """风险提示卡：结构性风险的知情说明（无'忽略'入口，风险不消失）。"""

    type: Literal["risk"] = "risk"
    key: str
    label: str
    why: str


class ReflectivePrompt(BaseModel):
    """反思提问卡：一句反问，回答走 /api/chat/turns（带 reply_to）。"""

    type: Literal["reflective"] = "reflective"
    question: str


CardUnion: TypeAlias = Annotated[
    DecisionCard | ClaimCard | RiskNote | ReflectivePrompt,
    Field(discriminator="type"),
]
"""四种卡片的类型判别联合：按 type 字段映射到具体模型。"""

CardJSON: TypeAlias = CardUnion
"""计划接口名（CardJSON）＝实现名（CardUnion），供后续端点引用。"""


class ChatTurn(BaseModel):
    """对话轮次：role + 文本 + 内嵌卡片 + 时间戳。"""

    role: Literal["user", "assistant"]
    text: str
    cards: list[CardUnion] = Field(default_factory=list)
    at: datetime
