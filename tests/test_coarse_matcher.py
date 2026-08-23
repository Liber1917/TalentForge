"""粗匹配器测试：围栏 JSON→Match；坏 JSON→LOW；非法 fit→LOW；claims 标记；gaps 解析。"""

from __future__ import annotations

from typing import Any

from talentforge.domain.job import Job
from talentforge.domain.match import FitLevel
from talentforge.domain.profile import NarrativeClaim, Profile
from talentforge.matcher.coarse import (
    COARSE_MATCH_SYSTEM_PROMPT,
    CoarseMatcher,
    _parse_gaps,
)

VALID_JSON = (
    "```json\n"
    '{"market_fit": "high", "growth_fit": "high", '
    '"reasoning": ["技能与岗位要求匹配"], '
    '"matched": ["Python"], "missing": ["Kubernetes"]}\n'
    "```"
)

VALID_JSON_WITH_GAPS = (
    "```json\n"
    '{"market_fit": "high", "growth_fit": "low", '
    '"reasoning": ["技能与岗位要求匹配"], '
    '"matched": ["Python"], "missing": ["Kubernetes"], '
    '"gaps": [{"skill": "Kubernetes", "severity": "major", '
    '"evidence": "JD 要求 K8s 部署经验，画像无容器编排记录"}]}\n'
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
    assert "gaps" in COARSE_MATCH_SYSTEM_PROMPT


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


async def test_gaps_from_llm_response_passthrough() -> None:
    """带 gaps 的响应 → match() 透传为 [{skill,severity,evidence}]。"""
    llm = FakeLLM(VALID_JSON_WITH_GAPS)
    matcher = CoarseMatcher(llm)
    result = await matcher.match(_make_profile(), _make_job(), _field_notes())

    assert result.gaps == [
        {
            "skill": "Kubernetes",
            "severity": "major",
            "evidence": "JD 要求 K8s 部署经验，画像无容器编排记录",
        }
    ]


async def test_old_response_without_gaps_defaults_to_empty() -> None:
    """旧响应（无 gaps 字段）→ gaps == []（兼容不炸）。"""
    llm = FakeLLM(VALID_JSON)
    matcher = CoarseMatcher(llm)
    result = await matcher.match(_make_profile(), _make_job(), _field_notes())

    assert result.gaps == []


def test_parse_gaps_non_list_returns_empty() -> None:
    """非 list（None/str/dict）→ []；list 内非 dict 条目跳过。"""
    assert _parse_gaps(None) == []
    assert _parse_gaps("Kubernetes") == []
    assert _parse_gaps({"skill": "Kubernetes"}) == []
    assert _parse_gaps(["Kubernetes", 42, None]) == []


def test_parse_gaps_invalid_severity_defaults_to_minor() -> None:
    """severity 非法/缺失 → minor；合法 major/minor 原样保留。"""
    gaps = _parse_gaps(
        [
            {"skill": "K8s", "severity": "critical", "evidence": "x"},
            {"skill": "Go", "evidence": "y"},
            {"skill": "Rust", "severity": "MAJOR", "evidence": "z"},
        ]
    )
    assert [g["severity"] for g in gaps] == ["minor", "minor", "major"]


def test_parse_gaps_truncates_entries_and_field_lengths() -> None:
    """超过 3 条截断；skill 截 40 字、evidence 截 120 字。"""
    entries = [
        {"skill": f"技能{i}", "severity": "major", "evidence": "依据"} for i in range(5)
    ]
    assert len(_parse_gaps(entries)) == 3

    long_fields = _parse_gaps(
        [{"skill": "K" * 60, "severity": "major", "evidence": "E" * 200}]
    )
    assert len(long_fields[0]["skill"]) == 40
    assert len(long_fields[0]["evidence"]) == 120
