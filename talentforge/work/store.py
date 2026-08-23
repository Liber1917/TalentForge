"""作品 artifacts JSON 存储（M5 spec §1.2：按 artifact_id merge + dismissed 驳回表）。"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from talentforge.domain.work import WorkArtifact

logger = logging.getLogger(__name__)

# 相对 cwd（同 feedback.FEEDBACK_LOG_PATH 风格；data/ 已 gitignore），可 monkeypatch；
# env TALENTFORGE_ARTIFACTS_PATH 可覆盖
ARTIFACTS_PATH = Path("data/artifacts.json")


def _resolve_path() -> Path:
    env = os.environ.get("TALENTFORGE_ARTIFACTS_PATH", "")
    return Path(env) if env else ARTIFACTS_PATH


class WorkStore:
    """artifacts.json 读写：upsert_all 按 artifact_id merge、dismissed 驳回幂等。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else _resolve_path()

    def _load(self) -> tuple[list[WorkArtifact], list[str]]:
        """读文件 → (artifacts, dismissed)；缺失静默空，损坏（JSON 坏/形状坏）告警按空处理。"""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return [], []
        except OSError as e:
            logger.warning("读取作品库 %s 失败: %s", self._path, e)
            return [], []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("作品库 %s 损坏，按空库处理: %s", self._path, e)
            return [], []
        if not isinstance(data, dict):
            logger.warning("作品库 %s 形状异常（需对象），按空库处理", self._path)
            return [], []
        artifacts: list[WorkArtifact] = []
        for item in data.get("artifacts") or []:
            try:
                artifacts.append(WorkArtifact.model_validate(item))
            except ValidationError as e:
                logger.warning("作品库 %s 含无效条目，已跳过: %s", self._path, e)
        dismissed = data.get("dismissed")
        if not isinstance(dismissed, list):
            dismissed = []
        return artifacts, [str(d) for d in dismissed]

    def _save(self, artifacts: list[WorkArtifact], dismissed: list[str]) -> None:
        payload = {
            "artifacts": [a.model_dump(mode="json") for a in artifacts],
            "dismissed": dismissed,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def upsert_all(self, artifacts: list[WorkArtifact]) -> int:
        """按 artifact_id merge（已存在整条更新），返回新增条数。"""
        existing, dismissed = self._load()
        by_id: dict[str, WorkArtifact] = {a.artifact_id: a for a in existing}
        added = 0
        for artifact in artifacts:
            if artifact.artifact_id not in by_id:
                added += 1
            by_id[artifact.artifact_id] = artifact
        self._save(list(by_id.values()), dismissed)
        return added

    def list_all(self) -> list[WorkArtifact]:
        """全部作品（含已驳回，展示层按 is_dismissed 过滤）。"""
        return self._load()[0]

    def dismiss(self, artifact_id: str) -> None:
        """驳回（幂等）：该 artifact 不再用于生成主张（spec §1.3 防线 c）。"""
        artifacts, dismissed = self._load()
        if artifact_id not in dismissed:
            dismissed.append(artifact_id)
        self._save(artifacts, dismissed)

    def is_dismissed(self, artifact_id: str) -> bool:
        return artifact_id in self._load()[1]
