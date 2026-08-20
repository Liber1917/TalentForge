from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from talentforge.domain.profile import Profile
from talentforge.domain.field import FieldModel
from talentforge.domain.job import Job
from talentforge.domain.competency import CompetencyModel
from talentforge.domain.match import Match
from talentforge.domain.feedback import FeedbackEvent


@runtime_checkable
class ProfileEngine(Protocol):
    """画像引擎（可拓展外围，O1 待定深度）。"""

    async def build_profile(self, explicit: dict[str, Any]) -> Profile: ...

    async def update_from_feedback(self, profile: Profile, event: FeedbackEvent) -> Profile: ...


@runtime_checkable
class CompetencyModelBuilder(Protocol):
    """胜任力建模（可拓展外围，O2 待理论审视）。"""

    async def build(self, role: str, level: str, jd_texts: list[str]) -> CompetencyModel: ...


@runtime_checkable
class FieldModeler(Protocol):
    """场域建模（可拓展外围，全新无上游）。"""

    def analyze(self, industry: str, company: str) -> FieldModel: ...


@runtime_checkable
class Matcher(Protocol):
    """三维匹配（可拓展外围，O2 量化方法待定）。"""

    async def match(
        self, profile: Profile, job: Job, competency: CompetencyModel, field: FieldModel
    ) -> Match: ...


@runtime_checkable
class SourceAdapter(Protocol):
    """岗位源适配器（可拓展外围，MVP=Boss 单源）。"""

    source: str

    async def scrape_jobs(self, query: str, limit: int = 20) -> list[Job]: ...
