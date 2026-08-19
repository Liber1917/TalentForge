from __future__ import annotations

from talentforge.domain.match import Match, FitLevel
from talentforge.domain.decision import Verdict


def decide(match: Match, deal_breakers: list[str]) -> Verdict:
    """二维象限 + 结构调制（spec §6.1）。

    二维象限：
      市场契合高 × 成长契合高 → apply
      市场契合高 × 成长契合低 → hold（舒适区）
      市场契合低 × 成长契合高 → hold（挑战型机会，交反思对话升级）
      市场契合低 × 成长契合低 → skip
    结构调制：
      命中 deal-breaker → skip（硬边界）
      存在结构性风险（未触 deal-breaker）→ 最高 hold（不投，先观望）
      缺失 fit → skip（评估不完整，不轻率决策）
    """
    risks = match.structural.risks
    hard = [r for r in risks if r in deal_breakers]
    if hard:
        return Verdict.SKIP

    mf, gf = match.market_fit, match.growth_fit
    if mf is None or gf is None:
        return Verdict.SKIP

    base = _quadrant(mf, gf)
    if risks and base == Verdict.APPLY:
        return Verdict.HOLD  # 结构性风险调制：有风险不投，先观望
    return base


def _quadrant(mf: FitLevel, gf: FitLevel) -> Verdict:
    if mf == FitLevel.HIGH and gf == FitLevel.HIGH:
        return Verdict.APPLY
    if mf == FitLevel.HIGH and gf == FitLevel.LOW:
        return Verdict.HOLD
    if mf == FitLevel.LOW and gf == FitLevel.HIGH:
        return Verdict.HOLD
    return Verdict.SKIP