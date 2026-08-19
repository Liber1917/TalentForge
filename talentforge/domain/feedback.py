from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from talentforge.domain.decision import Verdict


class FeedbackEvent(BaseModel):
    """反馈事件（闭环回流，D5/D11）。"""

    job_id: str
    decision_verdict: Verdict
    outcome: str | None = None  # interview | rejected | offer | no_response
    dialogue_note: str = ""  # 对话自述（叙事修正）
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))