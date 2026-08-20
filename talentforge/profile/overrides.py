"""显式偏好覆盖层：用户直改覆盖基础档案，原档不可变。

仅白名单字段可覆盖（skills/desired_roles/preferred_locations/deal_breakers/narrative）；
apply 返回副本（model_copy），基础档案永不被改写，重建档案时覆盖可安全重放。
"""
from __future__ import annotations

import json
from pathlib import Path

from talentforge.domain.profile import Profile

ALLOWED = {"skills", "desired_roles", "preferred_locations", "deal_breakers", "narrative"}


def load_overrides(path: Path) -> dict:
    """读取覆盖文件；文件缺失或 JSON 损坏时容错返回 {}。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_overrides(path: Path, d: dict) -> None:
    """写覆盖文件：UTF-8 中文原样落盘（ensure_ascii=False），缩进 2。"""
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_overrides(profile: Profile, o: dict) -> Profile:
    """生成应用覆盖后的有效档案副本；非白名单字段忽略，原档不动。"""
    return profile.model_copy(update={k: v for k, v in o.items() if k in ALLOWED})
