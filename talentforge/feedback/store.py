"""反馈事件 JSON 追加式存储（spec §1.2：幂等键 job_id+action，文件级容错）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from talentforge.domain.decision import Verdict
from talentforge.domain.feedback import FeedbackEvent

logger = logging.getLogger(__name__)

# 相对 cwd（同 cookies.CREDENTIALS_FILE 风格；data/ 已 gitignore），可 monkeypatch
FEEDBACK_LOG_PATH = Path("data/feedback_log.json")


class FeedbackStore:
    """feedback_log.json 读写：append 幂等合并、recent 倒序、summary 计数。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> list[FeedbackEvent]:
        """读文件 → 事件列表；缺失静默空表，损坏（读错/JSON 坏/形状坏）告警后按空表处理。"""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as e:
            logger.warning("读取反馈日志 %s 失败: %s", self._path, e)
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("反馈日志 %s 损坏，按空日志处理: %s", self._path, e)
            return []
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            logger.warning("反馈日志 %s 形状异常（需 events 数组），按空日志处理", self._path)
            return []
        events: list[FeedbackEvent] = []
        for item in data["events"]:
            try:
                events.append(FeedbackEvent.model_validate(item))
            except ValidationError as e:
                logger.warning("反馈日志 %s 含无效事件，已跳过: %s", self._path, e)
        return events

    def _save(self, events: list[FeedbackEvent]) -> None:
        payload = {"events": [e.model_dump(mode="json") for e in events]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append(self, event: FeedbackEvent) -> list[FeedbackEvent]:
        """幂等追加：同 job_id+action 已存在则整条更新（verdict/outcome/note/at），否则追加。

        返回全量事件列表。
        """
        events = self._load()
        for i, existing in enumerate(events):
            if existing.job_id == event.job_id and existing.action == event.action:
                events[i] = event
                break
        else:
            events.append(event)
        self._save(events)
        return events

    def recent(self, limit: int = 50) -> list[FeedbackEvent]:
        """按 at 倒序取最近 limit 条。"""
        return sorted(self._load(), key=lambda e: e.at, reverse=True)[:limit]

    def summary(self) -> dict[str, int]:
        """计数：n_decided 与 decided 内 apply/hold/skip 分布 + n_outcome。"""
        events = self._load()
        decided = [e for e in events if e.action == "decided"]
        return {
            "n_decided": len(decided),
            "n_apply": sum(1 for e in decided if e.decision_verdict == Verdict.APPLY),
            "n_hold": sum(1 for e in decided if e.decision_verdict == Verdict.HOLD),
            "n_skip": sum(1 for e in decided if e.decision_verdict == Verdict.SKIP),
            "n_outcome": sum(1 for e in events if e.action == "outcome"),
        }
