"""画像读写路径分离回归测试（M5 T5-user 教训钉桩）。

契约（talentforge/api/common.py）：
- 读链：env TALENTFORGE_PROFILE_PATH > 运行时 data/profile.json > 演示 fixture；
- 写链：env 显式时写 env 路径，否则写运行时路径——git 跟踪的演示 fixture 永不写入。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from talentforge.api import common
from talentforge.domain.profile import Profile


def test_save_without_env_writes_runtime_path_never_fixture(
    monkeypatch: Any, tmp_path: Path
) -> None:
    runtime = tmp_path / "data" / "profile.json"
    monkeypatch.setattr(common, "RUNTIME_PROFILE_PATH", runtime)
    monkeypatch.delenv("TALENTFORGE_PROFILE_PATH", raising=False)
    fixture_before = common.DEFAULT_PROFILE_PATH.read_text(encoding="utf-8")

    common.save_profile(Profile(name="张三"))

    assert runtime.exists()
    assert "张三" in runtime.read_text(encoding="utf-8")
    assert common.DEFAULT_PROFILE_PATH.read_text(encoding="utf-8") == fixture_before


def test_save_with_env_writes_env_path(monkeypatch: Any, tmp_path: Path) -> None:
    env_path = tmp_path / "env-profile.json"
    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(env_path))
    common.save_profile(Profile(name="李四"))
    assert "李四" in env_path.read_text(encoding="utf-8")


def test_read_fallback_chain_env_over_runtime_over_fixture(
    monkeypatch: Any, tmp_path: Path
) -> None:
    runtime = tmp_path / "runtime.json"
    env_path = tmp_path / "env.json"
    runtime.write_text(
        json.dumps({"name": "运行时画像"}, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(common, "RUNTIME_PROFILE_PATH", runtime)
    monkeypatch.delenv("TALENTFORGE_PROFILE_PATH", raising=False)

    assert common.profile_path() == runtime  # 运行时存在 → 覆盖 fixture
    assert common.load_profile().name == "运行时画像"

    monkeypatch.setenv("TALENTFORGE_PROFILE_PATH", str(env_path))  # env 最高
    assert common.profile_path() == env_path

    monkeypatch.setattr(common, "RUNTIME_PROFILE_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("TALENTFORGE_PROFILE_PATH", raising=False)
    assert common.profile_path() == common.DEFAULT_PROFILE_PATH  # 缺省回落 fixture
