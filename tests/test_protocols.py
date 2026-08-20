import pytest

from talentforge.protocols import ProfileEngine, Matcher, SourceAdapter
from talentforge.domain.profile import Profile
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.job import Job


class _FakeProfileEngine:
    async def build_profile(self, explicit: dict) -> Profile:
        return Profile(name=explicit["name"])

    async def update_from_feedback(self, profile: Profile, event: FeedbackEvent) -> Profile:
        return profile


@pytest.mark.asyncio
async def test_profile_engine_is_structurally_satisfied():
    engine = _FakeProfileEngine()
    assert isinstance(engine, ProfileEngine)
    p = await engine.build_profile({"name": "张三"})
    assert p.name == "张三"


class _FakeSource:
    source = "boss"

    async def scrape_jobs(self, query: str, limit: int = 20) -> list[Job]:
        return []


@pytest.mark.asyncio
async def test_source_adapter_protocol_attr():
    adapter = _FakeSource()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.source == "boss"
