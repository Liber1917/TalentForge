from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from talentforge.domain.profile import SalaryRange


class Job(BaseModel):
    """归一化岗位（扩展 jobclaw Job 模型 + 结构字段）。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str  # boss
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    salary: SalaryRange | None = None
    tags: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    company_type: str | None = None
    industry: str | None = None
    work_mode: str | None = None  # remote | onsite | hybrid
    risk_keys: list[str] = Field(default_factory=list)  # 命中场域风险，如 ["996"]
    metadata: dict[str, Any] = Field(default_factory=dict)