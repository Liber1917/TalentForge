"""作品域模型（M5 spec §1.1）：WorkArtifact — 事实层 + 规则分级层，LLM 零参与。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

WorkGrade = Literal["strong", "normal", "weak"]


class WorkArtifact(BaseModel):
    """作品条目：GitHub/Gitee 仓库或 arXiv 论文。

    facts 为采集器提取的结构化事实（repo: 语言分布/stars/commits/span_days/
    is_fork/pushed_at；paper: authors/first_author/year/venue/summary）；
    grade/grade_reasons 由 work_grading 规则表查表判定（可解释，D23 防线 b）。
    """

    artifact_id: str                     # "{platform}:{repo_full_name|paper_arxiv_id}"
    platform: Literal["github", "gitee", "arxiv"]
    kind: Literal["repo", "paper"]
    title: str                           # repo 名 / 论文标题
    url: str
    facts: dict[str, Any] = Field(default_factory=dict)
    grade: WorkGrade = "normal"          # "strong" | "normal" | "weak"（spec §2 规则表）
    grade_reasons: list[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
