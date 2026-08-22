from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from talentforge.domain.decision import Verdict


class FeedbackEvent(BaseModel):
    """反馈事件（闭环回流，D5/D11）。"""

    job_id: str
    job_title: str = ""  # 展示用（回流条目免反查库，M4 微扩）
    decision_verdict: Verdict
    outcome: str | None = None  # interview | rejected | offer | no_response
    action: Literal["decided", "outcome"] = "decided"  # 记录决策 vs 补报结果（M4 微扩）
    dialogue_note: str = ""  # 对话自述（叙事修正）
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))