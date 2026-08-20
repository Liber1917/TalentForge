"""岗位胜任力建模器（默认实现）：LLM 产出结构化六维 JSON。

方法源自 TalentModel-skill（资产见 assets/talent-model/），硬规则编码在
COMPETENCY_SYSTEM_PROMPT：一级维度=抽象特质非技能、校招潜力优先、技术词降级证据层。
"""
from __future__ import annotations

from talentforge.domain.competency import CompetencyDimension, CompetencyModel
from talentforge.llm.client import LLMClient
from talentforge.llm.json_utils import extract_json

COMPETENCY_SYSTEM_PROMPT = (
    "你是岗位胜任力建模器（方法源自 TalentModel-skill，见资产库）。"
    "硬规则：恰好 6 个一级维度；一级维度必须是人的稳定抽象特质，"
    "禁止技能/工具/技术栈/岗位职责（如 Python、系统设计、需求分析）；"
    "技能词降级到三级证据；校招/实习以潜力与可塑性为核心。"
    "只输出 JSON：{\"dimensions\":[{\"key\":\"D1\",\"name\":str,\"definition\":str,"
    "\"behaviors\":[str],\"evidence\":[str]}]}，每维度 behaviors≥2、evidence≥1。"
)

# 一级维度黑名单（技能/工具/职责词——命中即拒绝，防技能树陷阱）
DIMENSION_BLACKLIST: tuple[str, ...] = (
    "Python", "Java", "Go", "K8s", "CUDA", "系统设计", "需求分析", "项目管理", "算法实现",
)


class DefaultCompetencyModelBuilder:
    """依据 role/level/JD 文本构建结构化胜任力模型。"""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def build(self, role: str, level: str, jd_texts: list[str]) -> CompetencyModel:
        corpus = "\n---\n".join(t[:2000] for t in jd_texts)[:8000]
        raw = await self._llm.chat(
            COMPETENCY_SYSTEM_PROMPT,
            f"岗位：{role}\n级别：{level}\nJD材料：\n{corpus}",
        )
        data = extract_json(raw)
        dims = [CompetencyDimension.model_validate(d) for d in data.get("dimensions", [])][:6]
        for dim in dims:
            if any(term in dim.name for term in DIMENSION_BLACKLIST):
                raise ValueError(f"一级维度含技能/职责词（黑名单命中）：{dim.name}")
        return CompetencyModel(role=role, level=level, dimensions=dims)
