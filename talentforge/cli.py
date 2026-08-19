from __future__ import annotations

import click

from talentforge.decision.verdict import decide
from talentforge.domain.match import Match, FitLevel, StructuralAssessment


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


if __name__ == "__main__":
    main()
