"""M10 回测地基测试：决策落库 roundtrip / 过滤 / 导出。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from talentforge.cli import main
from talentforge.storage.db import init_db, insert_decision, list_decisions


def test_insert_and_list_decisions_roundtrip() -> None:
    conn = init_db(":memory:")
    insert_decision(
        conn,
        job_url="u1", source="boss", title="Python后端", company="A",
        verdict="hold", reason="方向偏差",
        gaps=[{"skill": "Go", "severity": "major"}],
        competency=[{"dimension": "韧性", "candidate_level": "strong"}],
        profile_snapshot={"name": "测试"},
    )
    rows = list_decisions(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["verdict"] == "hold"
    assert row["gaps"] == [{"skill": "Go", "severity": "major"}]
    assert row["competency"][0]["dimension"] == "韧性"
    assert row["profile_snapshot"] == {"name": "测试"}
    assert row["decided_at"]


def test_decisions_are_append_only() -> None:
    conn = init_db(":memory:")
    insert_decision(conn, "u1", "boss", "t", "A", "hold", "r", [], [], None)
    insert_decision(conn, "u1", "boss", "t", "A", "apply", "r2", [], [], None)
    rows = list_decisions(conn)
    assert len(rows) == 2
    assert rows[0]["verdict"] == "apply"  # 倒序：最新在前


def test_insert_decision_default_timestamp_is_utc_aware() -> None:
    """缺省 decided_at 必须是 UTC aware——events/jobs 全为 UTC，naive 本地时间
    与 aware 混存会让 ORDER BY decided_at / since 过滤（ISO 字符串比较）跨时区错乱。"""
    conn = init_db(":memory:")
    insert_decision(conn, "u1", "boss", "t", "A", "hold", "r", [], [])
    row = conn.execute("SELECT decided_at FROM decisions").fetchone()
    assert row[0].endswith("+00:00")


def test_list_decisions_since_filter() -> None:
    conn = init_db(":memory:")
    now = datetime.now().isoformat()
    old = (datetime.now() - timedelta(days=2)).isoformat()
    insert_decision(conn, "u1", "boss", "t", "A", "hold", "r", [], [], None, decided_at=old)
    insert_decision(conn, "u2", "boss", "t", "B", "apply", "r", [], [], None, decided_at=now)
    rows = list_decisions(conn, since=now)
    assert len(rows) == 1
    assert rows[0]["job_url"] == "u2"


def test_export_command_writes_json(tmp_path: Path) -> None:
    db_path = tmp_path / "t.db"
    conn = init_db(db_path)
    insert_decision(conn, "u1", "boss", "Python后端", "A", "hold", "方向偏差",
                    [{"skill": "Go"}], [{"dimension": "韧性"}], {"name": "测试"})
    conn.close()

    out = tmp_path / "export.json"
    runner = CliRunner()
    result = runner.invoke(main, ["export", "--db", str(db_path), "--out", str(out)])
    assert result.exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["n_decisions"] == 1
    assert data["decisions"][0]["verdict"] == "hold"
    assert data["decisions"][0]["gaps"][0]["skill"] == "Go"
    assert "api_key" not in json.dumps(data, ensure_ascii=False) or "api_key" not in data
    assert data["n_jobs"] == 0
