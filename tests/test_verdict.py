import pytest

from talentforge.domain.match import Match, FitLevel, StructuralAssessment
from talentforge.domain.decision import Verdict
from talentforge.decision.verdict import decide


def _match(mf, gf, risks=None):
    return Match(
        job_id="j",
        market_fit=mf,
        growth_fit=gf,
        structural=StructuralAssessment(risks=risks or []),
    )


def test_high_high_applies():
    assert decide(_match(FitLevel.HIGH, FitLevel.HIGH), []) == Verdict.APPLY


def test_high_low_is_hold_comfort_zone():
    assert decide(_match(FitLevel.HIGH, FitLevel.LOW), []) == Verdict.HOLD


def test_low_high_is_hold_challenge():
    assert decide(_match(FitLevel.LOW, FitLevel.HIGH), []) == Verdict.HOLD


def test_low_low_skips():
    assert decide(_match(FitLevel.LOW, FitLevel.LOW), []) == Verdict.SKIP


def test_deal_breaker_skips():
    assert decide(_match(FitLevel.HIGH, FitLevel.HIGH, risks=["996"]), ["996"]) == Verdict.SKIP


def test_structural_risk_downgrades_apply_to_hold():
    assert decide(_match(FitLevel.HIGH, FitLevel.HIGH, risks=["无社保"]), []) == Verdict.HOLD


def test_missing_fit_skips():
    assert decide(_match(None, FitLevel.HIGH), []) == Verdict.SKIP