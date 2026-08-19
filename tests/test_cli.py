from click.testing import CliRunner

from talentforge.cli import main


def test_decide_command_end_to_end():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["decide", "--market-fit", "high", "--growth-fit", "high"],
    )
    assert result.exit_code == 0
    assert "apply" in result.output


def test_decide_command_with_risk():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["decide", "--market-fit", "high", "--growth-fit", "high", "--risk", "无社保"],
    )
    assert result.exit_code == 0
    assert "hold" in result.output
