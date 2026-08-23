"""方向卡 directions JSON 存储（M7 spec §2）：快照整体替换 + 深谈修正写回。

同 work.store 模式：相对 cwd 的 data/ 路径、env TALENTFORGE_DIRECTIONS_PATH
可覆盖、可 monkeypatch；文件缺失/损坏（JSON 坏/形状坏）告警按空处理。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from talentforge.domain.direction import DirectionCard

logger = logging.getLogger(__name__)

# 相对 cwd（同 work.store.ARTIFACTS_PATH 风格；data/ 已 gitignore），可 monkeypatch；
# env TALENTFORGE_DIRECTIONS_PATH 可覆盖
DIRECTIONS_PATH = Path("data/directions.json")


def _resolve_path() -> Path:
    env = os.environ.get("TALENTFORGE_DIRECTIONS_PATH", "")
    return Path(env) if env else DIRECTIONS_PATH


class DirectionStore:
    """directions.json 读写：replace_all 快照替换（保修正卡）、upsert_card 深谈写回。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else _resolve_path()

    def _load(self) -> list[DirectionCard]:
        """读文件 → 方向卡列表；缺失静默空，损坏（JSON 坏/形状坏）告警按空处理。"""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as e:
            logger.warning("读取方向库 %s 失败: %s", self._path, e)
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("方向库 %s 损坏，按空处理: %s", self._path, e)
            return []
        if not isinstance(data, dict):
            logger.warning("方向库 %s 形状异常（需对象），按空处理", self._path)
            return []
        cards: list[DirectionCard] = []
        for item in data.get("directions") or []:
            try:
                cards.append(DirectionCard.model_validate(item))
            except ValidationError as e:
                logger.warning("方向库 %s 含无效条目，已跳过: %s", self._path, e)
        return cards

    def _save(self, cards: list[DirectionCard]) -> None:
        payload = {"directions": [c.model_dump(mode="json") for c in cards]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def replace_all(self, cards: list[DirectionCard]) -> None:
        """快照整体替换：旧快照卡清空，created_from 非空的深谈修正卡保留。

        修正卡与某张新快照卡同 card_id（同标题）时修正卡优先——深谈结论
        不被重新生成的快照冲掉（spec §3.3 溯源语义）。
        """
        by_id: dict[str, DirectionCard] = {c.card_id: c for c in cards}
        for revised in self._load():
            if revised.created_from:
                by_id[revised.card_id] = revised
        self._save(list(by_id.values()))

    def list_all(self) -> list[DirectionCard]:
        """全部方向卡（快照卡 + 深谈修正卡）。"""
        return self._load()

    def upsert_card(self, card: DirectionCard) -> None:
        """深谈修正写回：按 card_id 替换已存在卡，否则追加。"""
        cards = self._load()
        for i, existing in enumerate(cards):
            if existing.card_id == card.card_id:
                cards[i] = card
                break
        else:
            cards.append(card)
        self._save(cards)
