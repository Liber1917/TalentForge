"""overrides 层测试：白名单覆盖生效、原档不可变、IO 容错。"""
from __future__ import annotations

import json
from pathlib import Path

from talentforge.domain.profile import Profile
from talentforge.profile.overrides import apply_overrides, load_overrides, save_overrides


def test_override_wins_and_rebuild_safe():
    p = Profile(name="张三", skills=["Python"])
    eff = apply_overrides(p, {"skills": ["Python", "Rust"]})
    assert eff.skills == ["Python", "Rust"] and p.skills == ["Python"]  # 原档不动


def test_save_load_roundtrip(tmp_path: Path):
    path = tmp_path / "overrides.json"
    d = {"skills": ["Python", "Rust"], "deal_breakers": ["996"], "narrative": {"identity": "后端基础设施倾向"}}
    save_overrides(path, d)
    assert load_overrides(path) == d
    text = path.read_text(encoding="utf-8")
    assert "后端基础设施倾向" in text  # ensure_ascii=False：中文原样落盘
    assert json.loads(text) == d


def test_load_missing_file_returns_empty(tmp_path: Path):
    assert load_overrides(tmp_path / "nope.json") == {}


def test_load_corrupt_json_returns_empty(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{不是json", encoding="utf-8")
    assert load_overrides(path) == {}


def test_apply_ignores_non_allowed_keys():
    p = Profile(name="张三", skills=["Python"])
    eff = apply_overrides(p, {"name": "李四", "email": "a@b.c", "skills": ["Go"]})
    assert eff.name == "张三" and eff.email is None  # 非白名单字段不生效
    assert eff.skills == ["Go"]
