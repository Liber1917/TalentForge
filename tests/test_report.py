"""Task 6 决策报告测试：offline-file 端到端、generate_report 计数、_reflective_question 分支。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from talentforge.cli import main
from talentforge.domain.job import Job
from talentforge.domain.match import Match, StructuralAssessment
from talentforge.domain.profile import NarrativeIdentity, Profile
from talentforge.matcher.coarse import CoarseMatcher
from talentforge.report.generate import _reflective_question, generate_report
from talentforge.storage.db import init_db

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "talentforge" / "sources" / "fixtures"
FIXTURE_PATH = FIXTURES_DIR / "boss_search_page.html"
U = "https://www.zhipin.com/job_detail/r_{}.html"

VALID_MATCH_JSON = (
    "```json\n"
    '{"market_fit": "high", "growth_fit": "high", '
    '"reasoning": ["技能与岗位要求匹配"], '
    '"matched": ["Python"], "missing": ["Kubernetes"]}\n'
    "```"
)


class FakeLLM:
    """返回合法匹配 JSON，记录调用次数。"""

    def __init__(self, response: str = VALID_MATCH_JSON) -> None:
        self.response = response
        self.calls = 0

    async def chat(self, system: str, user: str) -> str:
        self.calls += 1
        return self.response


def _profile(**overrides: Any) -> Profile:
    defaults: dict[str, Any] = dict(name="张三", skills=["Python"])
    defaults.update(overrides)
    return Profile(**defaults)  # type: ignore[arg-type]


def _make_job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = dict(
        source="boss",
        title="Python 后端工程师",
        company="星辰科技",
        location="深圳",
        url="https://www.zhipin.com/job_detail/report_1.html",
        description="负责分布式系统开发",
        risk_keys=[],
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def test_report_command_offline_file_end_to_end(monkeypatch, tmp_path) -> None:
    """offline-file + FakeLLM 端到端：n_jobs==5、items 均含 verdict。"""
    monkeypatch.setattr("talentforge.cli._build_llm", lambda: FakeLLM())
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps({"name": "张三"}, ensure_ascii=False), encoding="utf-8")
    db_path = tmp_path / "talentforge.db"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "report",
            "--profile", str(profile_file),
            "--query", "后端工程师",
            "--city", "深圳",
            "--db", str(db_path),
            "--offline-file", str(FIXTURE_PATH),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["summary"]["n_jobs"] == 5
    assert report["summary"]["n_apply"] == 5
    assert report["summary"]["n_hold"] == 0
    assert report["summary"]["n_skip"] == 0
    assert len(report["items"]) == 5
    assert all(item["verdict"] in ("apply", "hold", "skip") for item in report["items"])
    assert db_path.exists(), "--db 指定的库应被写入（upsert 存库）"


async def test_generate_report_jobs_override_counts_deal_breaker_skip() -> None:
    """jobs 直喂：2 个 996 + 1 个 clean，996 命中 deal_breaker → skip，clean 高契合 → apply。"""
    profile = _profile(deal_breakers=["996"])
    jobs = [
        _make_job(id="j-a", url=U.format("a"), title="A", risk_keys=["996"]),
        _make_job(id="j-b", url=U.format("b"), title="B", risk_keys=["996"]),
        _make_job(id="j-c", url=U.format("c"), title="C", risk_keys=[]),
    ]

    report = await generate_report(
        profile,
        "后端工程师",
        "深圳",
        jobs=jobs,
        matcher=CoarseMatcher(FakeLLM()),
        conn=init_db(":memory:"),
    )

    assert report["summary"] == {"n_jobs": 3, "n_apply": 1, "n_hold": 0, "n_skip": 2}
    by_title = {item["title"]: item for item in report["items"]}
    assert by_title["A"]["verdict"] == "skip"
    assert by_title["B"]["verdict"] == "skip"
    assert by_title["C"]["verdict"] == "apply"
    assert by_title["A"]["risk_hits"] == ["996 工作制"]
    assert by_title["C"]["risk_hits"] == []
    assert by_title["A"]["reason"] == "技能与岗位要求匹配"
    assert by_title["C"]["reflective_question"].startswith("岗位要求")


def test_reflective_question_with_related_deal_breaker() -> None:
    """有 hit 且 deal_breaker 命中 → 引用硬边界权衡反问。"""
    profile = _profile(deal_breakers=["996"])
    match = Match(job_id="j1", structural=StructuralAssessment(risks=["996"]))
    field_notes: dict[str, object] = {
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

    question = _reflective_question(_make_job(), match, field_notes, profile)

    assert "996 工作制" in question
    assert "996" in question
    assert "硬边界" in question


def test_reflective_question_with_hit_generic() -> None:
    """有 hit 但 deal_breaker 不相关 → 通用反问。"""
    profile = _profile(deal_breakers=["竞业限制"])
    match = Match(job_id="j1", structural=StructuralAssessment(risks=["996"]))
    field_notes: dict[str, object] = {
        "hits": [
            {
                "key": "996",
                "label": "996 工作制",
                "why": "...",
                "severity": "deal_breaker_candidate",
            }
        ],
        "field_notes": "...",
    }

    question = _reflective_question(_make_job(), match, field_notes, profile)

    assert question == "你怎么看这份工作的996 工作制？"


def test_reflective_question_with_missing_dimension() -> None:
    """无 hit 且 missing 非空 → 补短板方向反问。"""
    profile = _profile()
    match = Match(job_id="j1", missing_dimensions=["Kubernetes"])
    field_notes: dict[str, object] = {"hits": [], "field_notes": ""}

    question = _reflective_question(_make_job(), match, field_notes, profile)

    assert question == "岗位要求 Kubernetes，这是你想补的方向吗？"


def test_reflective_question_fallback_to_deep_drive() -> None:
    """无 hit 无 missing → 深层驱动反问（取 deep_drives[0]）。"""
    profile = _profile(narrative=NarrativeIdentity(deep_drives=["技术深度"]))
    match = Match(job_id="j1")
    field_notes: dict[str, object] = {"hits": [], "field_notes": ""}

    question = _reflective_question(_make_job(), match, field_notes, profile)

    assert question == "这份工作推进你的技术深度吗？"


def test_reflective_question_fallback_without_deep_drive() -> None:
    """无 hit 无 missing 且无 deep_drives → 兜底长期方向反问。"""
    profile = _profile()
    match = Match(job_id="j1")
    field_notes: dict[str, object] = {"hits": [], "field_notes": ""}

    question = _reflective_question(_make_job(), match, field_notes, profile)

    assert question == "这份工作推进你的长期方向吗？"
