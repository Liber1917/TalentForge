"""competency builder 测试：六维解析 + 技能词黑名单拒绝。"""

from __future__ import annotations

import pytest

from talentforge.competency.builder import (
    COMPETENCY_SYSTEM_PROMPT,
    DIMENSION_BLACKLIST,
    DefaultCompetencyModelBuilder,
)

VALID_DIMS = {
    "dimensions": [
        {"key": f"D{i}", "name": name, "definition": "定义", "behaviors": ["b1", "b2"], "evidence": ["e1"]}
        for i, name in enumerate(
            ["认知复杂度", "内驱与目标感", "韧性", "协作意识", "学习敏捷", "工程严谨性"],
            start=1,
        )
    ]
}


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def chat(self, system: str, user: str) -> str:
        assert system == COMPETENCY_SYSTEM_PROMPT
        import json

        return "```json\n" + json.dumps(self._payload, ensure_ascii=False) + "\n```"


@pytest.mark.asyncio
async def test_build_six_dimensions():
    builder = DefaultCompetencyModelBuilder(llm=FakeLLM(VALID_DIMS))
    model = await builder.build("后端工程师", "校招", ["JD 文本"])
    assert len(model.dimensions) == 6
    assert model.dimensions[0].key == "D1"
    assert model.dimensions[0].name == "认知复杂度"
    assert model.role == "后端工程师" and model.level == "校招"


@pytest.mark.asyncio
async def test_blacklisted_dimension_rejected():
    bad = VALID_DIMS | {
        "dimensions": [
            {"key": "D1", "name": "Python开发能力", "definition": "x", "behaviors": ["b"], "evidence": ["e"]}
        ]
    }
    builder = DefaultCompetencyModelBuilder(llm=FakeLLM(bad))
    with pytest.raises(ValueError):
        await builder.build("后端工程师", "校招", ["JD"])


def test_blacklist_has_core_terms():
    assert {"Python", "系统设计", "需求分析"} <= set(DIMENSION_BLACKLIST)
