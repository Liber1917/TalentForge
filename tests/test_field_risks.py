"""场域风险信号库测试（命中映射 / 未命中空 / severity 分档 / 文案质量 / 未知 key 容错）。"""

from __future__ import annotations

from talentforge.domain.job import Job
from talentforge.field.risks import STRUCTURAL_RISKS, RiskInfo, assess


def _make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = dict(
        source="boss",
        title="Python 后端工程师",
        company="星辰科技",
        location="深圳",
        url="https://www.zhipin.com/job_detail/risk_1.html",
        description="负责分布式系统开发",
        risk_keys=["996"],
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def test_assess_hits_return_key_label_why_severity() -> None:
    job = _make_job(risk_keys=["996", "单休"])
    result = assess(job)
    hits = result["hits"]
    assert isinstance(hits, list)
    assert len(hits) == 2
    by_key = {hit["key"]: hit for hit in hits}
    assert "996" in by_key
    assert "单休" in by_key
    assert by_key["996"]["severity"] == "deal_breaker_candidate"
    assert by_key["单休"]["severity"] == "warning"
    assert by_key["996"]["label"] == "996 工作制"
    assert len(by_key["996"]["why"]) > 30
    assert result["field_notes"] != ""


def test_assess_deal_breaker_and_warning_severity_banding() -> None:
    job = _make_job(risk_keys=["996", "大小周", "竞业限制", "加班费模糊"])
    hits = {hit["key"]: hit["severity"] for hit in assess(job)["hits"]}  # type: ignore[index, assignment]
    assert hits["996"] == "deal_breaker_candidate"
    assert hits["竞业限制"] == "deal_breaker_candidate"
    assert hits["大小周"] == "warning"
    assert hits["加班费模糊"] == "warning"


def test_assess_no_risks_returns_empty() -> None:
    result = assess(_make_job(risk_keys=[]))
    assert result["hits"] == []
    assert result["field_notes"] == ""


def test_assess_unknown_risk_key_is_ignored() -> None:
    result = assess(_make_job(risk_keys=["未来会有的新风险", "异星合约"]))
    assert result["hits"] == []
    assert result["field_notes"] == ""
    # 未知 key 与已知 key 混合：只返回已知项，不炸
    mixed = assess(_make_job(risk_keys=["未收录风险", "996"]))
    assert [hit["key"] for hit in mixed["hits"]] == ["996"]  # type: ignore[index, union-attr]


def test_structural_risks_at_least_8_with_substantive_why() -> None:
    assert len(STRUCTURAL_RISKS) >= 8
    assert all(isinstance(info, RiskInfo) for info in STRUCTURAL_RISKS.values())
    for key, info in STRUCTURAL_RISKS.items():
        assert info.key == key
        assert len(info.label) > 0
        assert len(info.why) > 30, f"{key} 的 why 文案过短（防偷懒）"
        assert info.severity in ("warning", "deal_breaker_candidate")


def test_field_notes_sums_multiple_whys() -> None:
    result = assess(_make_job(risk_keys=["996", "无社保"]))
    notes = result["field_notes"]
    assert isinstance(notes, str)
    assert STRUCTURAL_RISKS["996"].why in notes
    assert STRUCTURAL_RISKS["无社保"].why in notes
