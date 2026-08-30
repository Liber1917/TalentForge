"""可拓展外围的 Protocol 边界（D15：核心只依赖 schema 类型，不依赖具体实现）。

签名以现实实现对齐（D25 后）：Matcher.match 即 CoarseMatcher 的实际签名。
FieldModeler / SourceAdapter 已移除——前者全仓库无实现（场域走 field.risks
纯函数），后者随 D25 服务器侧抓取一并消亡（扩展为唯一采集通道）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from talentforge.domain.profile import Profile
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.job import Job
from talentforge.domain.competency import CompetencyModel
from talentforge.domain.match import Match


@runtime_checkable
class ProfileEngine(Protocol):
    """画像引擎（可拓展外围，O1 已收口：方案C+α机制）。"""

    async def build_profile(self, explicit: dict[str, Any]) -> Profile: ...

    async def update_from_feedback(self, profile: Profile, event: FeedbackEvent) -> Profile: ...


@runtime_checkable
class CompetencyModelBuilder(Protocol):
    """胜任力建模（可拓展外围，O2 已收口：D20）。"""

    async def build(self, role: str, level: str, jd_texts: list[str]) -> CompetencyModel: ...


@runtime_checkable
class Matcher(Protocol):
    """三维匹配（可拓展外围，O2 序数精排待定）。

    签名对齐 CoarseMatcher 现实：field_notes 为 field.risks.assess 的产物，
    known_dimensions 为岗位簇已固化的胜任力维度（M9 复用框架）。
    """

    async def match(
        self,
        profile: Profile,
        job: Job,
        field_notes: dict[str, object],
        known_dimensions: list[str] | None = None,
    ) -> Match: ...
