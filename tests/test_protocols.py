"""D15 协议契约：真实实现满足协议，且协议签名与现实对齐。

runtime_checkable 的 isinstance 只查方法名不查签名——签名漂移必须用
inspect 逐参数比对（protocols.py 曾因此纸面化：Matcher 协议签名与
CoarseMatcher 实现不匹配，全仓库无人发现）。
"""

from __future__ import annotations

import inspect

from talentforge.competency.builder import DefaultCompetencyModelBuilder
from talentforge.matcher.coarse import CoarseMatcher
from talentforge.profile.engine import DefaultProfileEngine
from talentforge.protocols import CompetencyModelBuilder, Matcher, ProfileEngine


class _FakeLLM:
    async def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        return ""


def test_matcher_protocol_signature_matches_reality() -> None:
    """协议签名 = CoarseMatcher 现实签名（D25 后：field_notes + known_dimensions）。"""
    proto = list(inspect.signature(Matcher.match).parameters)
    real = list(inspect.signature(CoarseMatcher.match).parameters)
    assert proto == real, f"协议签名漂移：Matcher{proto} != CoarseMatcher{real}"


def test_real_matcher_satisfies_protocol() -> None:
    assert isinstance(CoarseMatcher(_FakeLLM()), Matcher)


def test_real_profile_engine_satisfies_protocol() -> None:
    assert isinstance(DefaultProfileEngine(_FakeLLM()), ProfileEngine)


def test_real_competency_builder_satisfies_protocol() -> None:
    assert isinstance(DefaultCompetencyModelBuilder(_FakeLLM()), CompetencyModelBuilder)
