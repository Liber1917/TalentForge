"""M4 Task 1 测试：FeedbackStore 幂等/倒序/统计/容错 + FeedbackPipeline 回流规则逐条。

规则表来源 docs/spec-m4-feedback.md §1.3（显示性偏好保守回流，全规则版无 LLM）；
段位映射：max_annual 换算万 → ordering 项数字区间闭匹配（"40万以上"= ≥40万）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from talentforge.domain.decision import Verdict
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.job import Job
from talentforge.domain.profile import (
    NarrativeClaim,
    OrdinalPreference,
    Profile,
    SalaryRange,
)
from talentforge.feedback.engine import FeedbackPipeline
from talentforge.feedback.store import FeedbackStore

AT = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
CLAIM_TEXT = "对高并发后端服务有实战积累"


def _event(**overrides: Any) -> FeedbackEvent:
    defaults: dict[str, Any] = dict(
        job_id="j1",
        job_title="星辰科技",
        decision_verdict=Verdict.APPLY,
        action="decided",
        at=AT,
    )
    defaults.update(overrides)
    return FeedbackEvent(**defaults)


def _job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = dict(
        source="boss",
        title="Python 后端工程师",
        company="星辰科技",
        location="深圳·南山",
        url="https://example.com/j1",
        salary=SalaryRange(min_annual=300000, max_annual=350000),
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def _profile(ordering: list[str] | None = None, claim: str = "") -> Profile:
    return Profile(
        name="张三",
        utility_preferences={
            "薪资": OrdinalPreference(
                attribute="薪资", ordering=ordering or ["40万以上", "30-40万", "20-30万"]
            )
        },
        narrative_claims=[NarrativeClaim(text=claim)] if claim else [],
    )


# ---------- FeedbackStore ----------


def test_store_append_is_idempotent_on_job_and_action(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "feedback_log.json")
    first = store.append(_event(decision_verdict=Verdict.HOLD, dialogue_note="观望"))
    assert len(first) == 1
    second = store.append(_event(decision_verdict=Verdict.APPLY))
    assert len(second) == 1
    assert second[0].decision_verdict == Verdict.APPLY
    assert second[0].dialogue_note == ""  # 整条更新为最新事件


def test_store_append_keeps_different_actions_separate(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "feedback_log.json")
    store.append(_event())
    events = store.append(_event(action="outcome", outcome="offer"))
    assert len(events) == 2


def test_store_recent_sorted_desc_with_limit(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "feedback_log.json")
    store.append(_event(job_id="a", at=datetime(2026, 8, 20, tzinfo=timezone.utc)))
    store.append(_event(job_id="b"))
    store.append(_event(job_id="c", at=datetime(2026, 8, 21, tzinfo=timezone.utc)))
    recent = store.recent(limit=2)
    assert [e.job_id for e in recent] == ["b", "c"]


def test_store_summary_counts(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "feedback_log.json")
    store.append(_event(job_id="a"))
    store.append(_event(job_id="b", decision_verdict=Verdict.HOLD))
    store.append(_event(job_id="c", decision_verdict=Verdict.SKIP))
    store.append(_event(job_id="a", action="outcome", outcome="offer"))
    assert store.summary() == {
        "n_decided": 3,
        "n_apply": 1,
        "n_hold": 1,
        "n_skip": 1,
        "n_outcome": 1,
    }


def test_store_tolerates_missing_and_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "feedback_log.json"
    store = FeedbackStore(path)
    assert store.recent() == []  # 文件缺失 → 空表
    path.write_text("not-json{", encoding="utf-8")
    events = store.append(_event())  # 损坏 → 告警后按空表处理，可继续写入
    assert len(events) == 1
    assert FeedbackStore(path).recent()[0].job_id == "j1"


# ---------- FeedbackEvent 域模型微扩 ----------


def test_feedback_event_new_fields_default_for_old_data() -> None:
    ev = FeedbackEvent.model_validate({"job_id": "j1", "decision_verdict": "apply"})
    assert ev.job_title == ""
    assert ev.action == "decided"


# ---------- FeedbackPipeline：偏好回流规则表 ----------


def test_decided_apply_appends_evidence_without_reorder() -> None:
    new, changes = FeedbackPipeline().apply(_profile(), _event(), _job())
    assert new.utility_preferences["薪资"].ordering == ["40万以上", "30-40万", "20-30万"]
    assert new.utility_preferences["薪资"].evidence == ["2026-08-22 apply 星辰科技(30-35万/年)"]
    assert changes == ["evidence +1: 2026-08-22 apply 星辰科技(30-35万/年)"]


def test_decided_hold_also_marks_tier_evidence() -> None:
    new, _ = FeedbackPipeline().apply(
        _profile(), _event(decision_verdict=Verdict.HOLD), _job()
    )
    assert new.utility_preferences["薪资"].evidence[0].startswith("2026-08-22 hold 星辰科技")


def test_outcome_offer_moves_tier_up_one_position() -> None:
    new, changes = FeedbackPipeline().apply(
        _profile(), _event(action="outcome", outcome="offer"), _job()
    )
    assert new.utility_preferences["薪资"].ordering == ["30-40万", "40万以上", "20-30万"]
    assert changes == [
        "salary ordering: '30-40万' +1 位（offer）",
        "evidence +1: 2026-08-22 offer 星辰科技(30-35万/年)",
    ]


def test_outcome_interview_also_upgrades() -> None:
    new, _ = FeedbackPipeline().apply(
        _profile(), _event(action="outcome", outcome="interview"), _job()
    )
    assert new.utility_preferences["薪资"].ordering[0] == "30-40万"


def test_negative_outcome_does_not_move_ordering() -> None:
    new, changes = FeedbackPipeline().apply(
        _profile(), _event(action="outcome", outcome="rejected"), _job()
    )
    assert new.utility_preferences["薪资"].ordering == ["40万以上", "30-40万", "20-30万"]
    assert changes == []


def test_outcome_offer_when_tier_first_keeps_position() -> None:
    new, changes = FeedbackPipeline().apply(
        _profile(ordering=["30-40万", "40万以上", "20-30万"]),
        _event(action="outcome", outcome="offer"),
        _job(),
    )
    assert new.utility_preferences["薪资"].ordering == ["30-40万", "40万以上", "20-30万"]
    assert changes == ["evidence +1: 2026-08-22 offer 星辰科技(30-35万/年)"]


def test_decided_skip_with_note_only_annotates_evidence() -> None:
    new, changes = FeedbackPipeline().apply(
        _profile(),
        _event(decision_verdict=Verdict.SKIP, dialogue_note="薪资低于预期且加班文化重"),
        _job(),
    )
    assert new.utility_preferences["薪资"].ordering == ["40万以上", "30-40万", "20-30万"]
    assert new.utility_preferences["薪资"].evidence == [
        "2026-08-22 skip 星辰科技: 薪资低于预期且加班文化重"
    ]
    assert changes == ["evidence +1: 2026-08-22 skip 星辰科技: 薪资低于预期且加班文化重"]


def test_skip_note_truncated_to_40_chars() -> None:
    new, _ = FeedbackPipeline().apply(
        _profile(),
        _event(decision_verdict=Verdict.SKIP, dialogue_note="薪" * 60),
        _job(),
    )
    assert new.utility_preferences["薪资"].evidence == [
        f"2026-08-22 skip 星辰科技: {'薪' * 40}"
    ]


def test_tier_miss_skips_salary_but_keeps_narrative() -> None:
    job = _job(salary=SalaryRange(min_annual=550000, max_annual=600000))
    new, changes = FeedbackPipeline().apply(
        _profile(ordering=["20-30万"], claim=CLAIM_TEXT),
        _event(dialogue_note="面试确认我对高并发后端服务很熟"),
        job,
    )
    assert new.utility_preferences["薪资"].ordering == ["20-30万"]
    assert new.utility_preferences["薪资"].evidence == []
    assert new.narrative_claims[0].evidence_count == 1
    assert new.narrative_claims[0].sources[-1].kind == "feedback"
    assert changes and changes[0].startswith("叙事主张证据 +1")


def test_open_tier_matches_above_threshold() -> None:
    job = _job(salary=SalaryRange(min_annual=420000, max_annual=450000))
    new, _ = FeedbackPipeline().apply(
        _profile(ordering=["30-40万", "40万以上", "20-30万"]),
        _event(action="outcome", outcome="offer"),
        job,
    )
    assert new.utility_preferences["薪资"].ordering == ["40万以上", "30-40万", "20-30万"]


def test_tier_boundary_hits_first_ordering_match() -> None:
    # 40万整在闭区间 "30-40万"(≤40) 与开区间 "40万以上"(≥40) 都命中 → 取 ordering 靠前者
    job = _job(salary=SalaryRange(min_annual=300000, max_annual=400000))
    new, _ = FeedbackPipeline().apply(
        _profile(ordering=["20-30万", "30-40万", "40万以上"]),
        _event(action="outcome", outcome="offer"),
        job,
    )
    assert new.utility_preferences["薪资"].ordering == ["30-40万", "20-30万", "40万以上"]


def test_missing_job_skips_tier_rules() -> None:
    new, changes = FeedbackPipeline().apply(
        _profile(claim=CLAIM_TEXT),
        _event(dialogue_note="我对高并发后端服务有信心"),
        None,
    )
    assert new.utility_preferences["薪资"].evidence == []
    assert new.narrative_claims[0].evidence_count == 1
    assert changes == ["叙事主张证据 +1: " + CLAIM_TEXT]


# ---------- FeedbackPipeline：叙事修正 + 纯函数性 ----------


def test_narrative_miss_leaves_claims_untouched() -> None:
    new, changes = FeedbackPipeline().apply(
        _profile(claim=CLAIM_TEXT), _event(dialogue_note="今天天气不错"), _job()
    )
    assert new.narrative_claims[0].evidence_count == 0
    assert changes == ["evidence +1: 2026-08-22 apply 星辰科技(30-35万/年)"]


def test_narrative_only_touches_trial_claims() -> None:
    p = _profile(claim=CLAIM_TEXT)
    p.narrative_claims[0].state = "active"
    new, changes = FeedbackPipeline().apply(
        p, _event(dialogue_note="我对高并发后端服务有信心"), _job()
    )
    assert new.narrative_claims[0].evidence_count == 0
    assert not any(c.startswith("叙事主张") for c in changes)


def test_apply_does_not_mutate_input_profile() -> None:
    p = _profile(claim=CLAIM_TEXT)
    snapshot = p.model_dump_json()
    new, _ = FeedbackPipeline().apply(
        p,
        _event(
            action="outcome",
            outcome="offer",
            dialogue_note="我对高并发后端服务有信心",
        ),
        _job(),
    )
    assert p.model_dump_json() == snapshot
    assert new is not p
    assert new.utility_preferences["薪资"] is not p.utility_preferences["薪资"]


# ---------- 旧数据兼容 ----------


def test_old_profile_without_evidence_field_is_compatible() -> None:
    legacy = {
        "name": "张三",
        "utility_preferences": {
            "薪资": {"attribute": "薪资", "ordering": ["40万以上", "30-40万", "20-30万"]}
        },
    }
    p = Profile.model_validate(legacy)
    assert p.utility_preferences["薪资"].evidence == []
    new, changes = FeedbackPipeline().apply(p, _event(), _job())
    assert new.utility_preferences["薪资"].evidence
    assert changes
