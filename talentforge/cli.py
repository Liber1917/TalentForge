from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from talentforge.competency.builder import DefaultCompetencyModelBuilder
from talentforge.decision.verdict import decide
from talentforge.domain.competency import CompetencyModel
from talentforge.domain.match import Match, FitLevel, StructuralAssessment
from talentforge.domain.profile import Profile
from talentforge.llm.client import EnvLLMClient, LLMClient
from talentforge.profile.engine import DefaultProfileEngine


def _build_llm() -> LLMClient:
    """构造 LLM 客户端（独立函数便于测试 monkeypatch）。"""
    return EnvLLMClient()


@click.group()
def main() -> None:
    """TalentForge — 锻造人才的求职决策助手。"""


@main.command("decide")
@click.option("--market-fit", type=click.Choice(["high", "low"]), required=True)
@click.option("--growth-fit", type=click.Choice(["high", "low"]), required=True)
@click.option("--risk", multiple=True, help="命中的结构性风险，如 996、无社保")
@click.option("--deal-breaker", multiple=True, help="用户 deal-breaker，命中即不投")
def decide_command(market_fit: str, growth_fit: str, risk: tuple[str, ...], deal_breaker: tuple[str, ...]) -> None:
    """M0 walking skeleton：给定匹配信号，输出三元决策。"""
    match = Match(
        job_id="demo",
        market_fit=FitLevel(market_fit),
        growth_fit=FitLevel(growth_fit),
        structural=StructuralAssessment(risks=list(risk)),
    )
    verdict = decide(match, list(deal_breaker))
    click.echo(f"verdict={verdict.value}")


async def _run_profile_build(explicit: dict[str, Any]) -> Profile:
    engine = DefaultProfileEngine(llm=_build_llm())
    return await engine.build_profile(explicit)


@main.command("profile-build")
@click.option("--name", type=str, default="", help="候选人姓名")
@click.option("--resume-file", type=click.Path(exists=True, dir_okay=False), required=True, help="简历文本文件")
@click.option("--explicit-json", type=click.Path(exists=True, dir_okay=False), default=None, help="显式画像 JSON（八格/效用等）")
def profile_build(name: str, resume_file: str, explicit_json: str | None) -> None:
    """简历 bootstrap 生成画像，输出 Profile JSON 摘要到 stdout。"""
    resume_text = Path(resume_file).read_text(encoding="utf-8")
    if explicit_json:
        explicit = json.loads(Path(explicit_json).read_text(encoding="utf-8"))
    else:
        explicit = {"name": name}
    explicit.setdefault("resume_text", resume_text)
    profile = asyncio.run(_run_profile_build(explicit))
    click.echo(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))


async def _run_competency_build(role: str, level: str, jd_text: str) -> CompetencyModel:
    builder = DefaultCompetencyModelBuilder(llm=_build_llm())
    return await builder.build(role, level, [jd_text])


@main.command("competency")
@click.option("--role", required=True, help="目标岗位")
@click.option("--level", required=True, help="招聘级别，如 校招/社招")
@click.option("--jd-file", type=click.Path(exists=True, dir_okay=False), required=True, help="JD 文本文件")
def competency_command(role: str, level: str, jd_file: str) -> None:
    """构建岗位胜任力模型（六维结构化 JSON）到 stdout。"""
    jd_text = Path(jd_file).read_text(encoding="utf-8")
    model = asyncio.run(_run_competency_build(role, level, jd_text))
    click.echo(json.dumps(model.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
