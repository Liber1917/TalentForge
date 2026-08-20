"""CLI M1 命令测试：profile-build / competency（monkeypatch _build_llm → FakeLLM）。"""

from __future__ import annotations

import json

from click.testing import CliRunner

from talentforge.cli import main

PROFILE_JSON = {
    "identity": "后端基础设施倾向",
    "values": [],
    "deep_drives": [],
    "cognitive_style": "",
    "claims": [],
}

VALID_DIMS = {
    "dimensions": [
        {"key": f"D{i}", "name": name, "definition": "定义", "behaviors": ["b1", "b2"], "evidence": ["e1"]}
        for i, name in enumerate(
            ["认知复杂度", "内驱与目标感", "韧性", "协作意识", "学习敏捷", "工程严谨性"],
            start=1,
        )
    ]
}


class FakeProfileLLM:
    async def chat(self, system: str, user: str) -> str:
        return "```json\n" + json.dumps(PROFILE_JSON, ensure_ascii=False) + "\n```"


class FakeCompetencyLLM:
    async def chat(self, system: str, user: str) -> str:
        return "```json\n" + json.dumps(VALID_DIMS, ensure_ascii=False) + "\n```"


def test_profile_build_command(monkeypatch, tmp_path):
    monkeypatch.setattr("talentforge.cli._build_llm", lambda: FakeProfileLLM())
    resume = tmp_path / "resume.txt"
    resume.write_text("做过分布式存储课程项目", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["profile-build", "--resume-file", str(resume)])
    assert result.exit_code == 0
    assert '"identity"' in result.output


def test_competency_command(monkeypatch, tmp_path):
    monkeypatch.setattr("talentforge.cli._build_llm", lambda: FakeCompetencyLLM())
    jd = tmp_path / "jd.txt"
    jd.write_text("负责后端服务研发，追求工程严谨", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["competency", "--role", "后端工程师", "--level", "校招", "--jd-file", str(jd)],
    )
    assert result.exit_code == 0
    assert '"dimensions"' in result.output
