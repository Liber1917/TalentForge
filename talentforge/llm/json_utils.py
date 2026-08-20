"""结构化输出容错（仿 OpenBiliClaw llm/json_utils 思路）：直接/围栏/散文包裹。"""
from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict:
    raw = str(text or "").strip()
    for candidate in _candidates(raw):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("输出中未找到 JSON 对象")


def _candidates(raw: str) -> list[str]:
    out = [raw]
    fenced = _FENCE_RE.search(raw)
    if fenced:
        out.append(fenced.group(1))
    first, last = raw.find("{"), raw.rfind("}")
    if first != -1 and last > first:
        out.append(raw[first : last + 1])
    return out
