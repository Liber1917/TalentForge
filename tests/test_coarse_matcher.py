"""粗匹配器测试：围栏 JSON→Match；坏 JSON→默认 LOW；非法 fit→LOW；[已验证]/[待验证] 标记。"""

from __future__ import annotations

from typing import Any

from talentforge.domain.job import Job
from talentforge.domain.match import FitLevel
from talentforge.domain.profile import NarrativeClaim, Profile
from talentforge.matcher.coarse import COARSE_MATCH_SYSTEM_PROMPT, CoarseMatcher

VALID_JSON = (
    "```json\n"
    '{"market_fit": "high", "growth_fit": "high", '
    '"reasoning": ["技能与岗位要求匹配"], '
    '"matched": ["Python"], "missing": ["Kubernetes"]}\n'
    "```"
)


class FakeLLM:
    """记录 system/user 参数，返回预设响应。"""

    def __init__(self, response: str) -> None:
        self.response = response
        self.systems: list[str] = []
        self.users: list[str] = []

    async def chat(self, system: str, user: str) -> str:
        self.systems.append(system)
        self.users.append(user)
        return self.response


def _make_profile(**overrides: Any) -> Profile:
    defaults: dict[str, Any] = dict(
        name="张三",
        years_experience=5.0,
        skills=["Python", "Django"],
        narrative_claims=[
            NarrativeClaim(text="主导过分布式系统重构", state="active"),
            NarrativeClaim(text="熟悉量化交易策略", state="trial"),
        ],
    )
    defaults.update(overrides)
    return Profile(**defaults)  # type: ignore[arg-type]


def _make_job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = dict(
        id="job-1",
        source="boss",
        title="Python 后端工程师",
        company="星辰科技",
        location="深圳",
        url="https://www.zhipin.com/job_detail/x.html",
        description="负责分布式系统开发，要求 Python。",
        tags=["Python", "后端"],
        risk_keys=["996"],
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def _field_notes() -> dict[str, object]:
    return {
        "hits": [
            {
                "key": "996",
                "label": "996 工作制",
                "why": "超出法定工时部分通常不支付对价。",
                "severity": "deal_breaker_candidate",
            }
        ],
        "field_notes": "超出法定工时部分通常不支付对价。",
    }


async def test_valid_fenced_json_produces_high_high_match() -> None:
    """围栏 JSON → market/growth 均 HIGH、reasoning 非空、risks 从 field_notes 提取。"""
    llm = FakeLLM(VALID_JSON)
    matcher = CoarseMatcher(llm)
    result = await matcher.match(_make_profile(), _make_job(), _field_notes())

    assert result.job_id == "job-1"
    assert result.market_fit == FitLevel.HIGH
    assert result.growth_fit == FitLevel.HIGH
    assert result.reasoning
    assert result.matched_dimensions == ["Python"]
    assert result.missing_dimensions == ["Kubernetes"]
    assert result.structural.risks == ["996"]


async def test_system_prompt_is_static_module_constant() -> None:
    """matcher 把静态 system 原样传给 LLM（prompt-cache 约定），user 才含变量。"""
    llm = FakeLLM(VALID_JSON)
    matcher = CoarseMatcher(llm)
    await matcher.match(_make_profile(), _make_job(), _field_notes())

    assert llm.systems == [COARSE_MATCH_SYSTEM_PROMPT]
    assert "market_fit" in COARSE_MATCH_SYSTEM_PROMPT
    assert "growth_fit" in COARSE_MATCH_SYSTEM_PROMPT
    assert "high|low" in COARSE_MATCH_SYSTEM_PROMPT


async def test_bad_json_falls_back_to_low_with_error_reason() -> None:
    """extract_json 失败 → 默认 LOW，reasoning 附错因。"""
    llm = FakeLLM("完全不是 JSON，只有一段散文")
    matcher = CoarseMatcher(llm)
    result = await matcher.match(_make_profile(), _make_job(), _field_notes())

    assert result.market_fit == FitLevel.LOW
    assert result.growth_fit == FitLevel.LOW
    assert result.reasoning
    assert "匹配评估失败" in result.reasoning[0]


async def test_invalid_fit_string_defaults_to_low() -> None:
    """非法 fit 字符串（如 medium）→ 默认 LOW；合法值不受影响。"""
    llm = FakeLLM(
        '{"market_fit": "medium", "growth_fit": "high", '
        '"reasoning": [], "matched": [], "missing": []}'
    )
    matcher = CoarseMatcher(llm)
    result = await matcher.match(_make_profile(), _make_job(), _field_notes())

    assert result.market_fit == FitLevel.LOW
    assert result.growth_fit == FitLevel.HIGH


async def test_user_message_marks_verified_and_pending_claims() -> None:
    """active 主张标 [已验证]、trial 主张标 [待验证]，并带 job/risk 摘要。"""
    llm = FakeLLM(VALID_JSON)
    matcher = CoarseMatcher(llm)
    await matcher.match(_make_profile(), _make_job(), _field_notes())

    user = llm.users[0]
    assert "[已验证]" in user
    assert "[待验证]" in user
    assert "主导过分布式系统重构" in user
    assert "熟悉量化交易策略" in user
    assert "Python 后端工程师" in user
    assert "996" in user
