"""岗位胜任力聚类 + 模型缓存（M9：预埋聚类接口）。

设计（继承 TalentModel-skill 岗位建模）：
- CompetencyClusterer（Protocol）：输入岗位集合 → 簇列表；`find_cluster` 判定
  新岗位是否命中已有簇（命中 → 复用该簇模型，避免重复 LLM 建模）。
- RuleCompetencyClusterer（MVP 实现）：title 归一化（去符号/行业词）+ 技能词
  重叠率 ≥ 阈值 → 同簇。零依赖、可测。
- 预留升级：未来可换 EmbeddingClusterer（LLM embedding + 余弦 + 密度聚类）
  实现同一 Protocol，调用方（generate.py）不改。缓存文件记 clusterer_version，
  换算法后旧缓存自动失效（版本不匹配即重建）。

缓存：data/competency_models.json（gitignored，同 project_suggest 模式），
按 role_key 存模型；写链永不落 git 跟踪文件。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Protocol

from talentforge.domain.competency import CompetencyCluster, CompetencyModel
from talentforge.domain.job import Job

logger = logging.getLogger(__name__)

CACHE_ENV = "TALENTFORGE_COMPETENCY_CACHE"
RUNTIME_CACHE_PATH = Path("data/competency_models.json")

# 归一化时剔除的行业/通用后缀词（避免「后端开发」与「后端专家」拆成两簇）
_TITLE_STOPWORDS = (
    "工程师", "专家", "开发", "研发", "岗位", "招聘", "校招", "社招", "实习",
    "初级", "中级", "高级", "资深",
)
_TITLE_SYMBOL_RE = re.compile(r"[()（）\[\]【】·\-—_/\\\s+]+")
# 技能词提取：白名单（词汇本身无歧义，允许大小写变体）+ 科技词形 token——
# 全大写缩写 / 驼峰 / 含数字 / 含技术符号（C++、Node.js、K8s、gRPC）。
# 词形分支大小写敏感：曾用全局 IGNORECASE 使 [A-Z] 锚失效，任意英文单词
# 都算技能词，英文样板话术污染重叠率 → 不相关岗位并簇（rule-v2 修复）。
# 尾部用 (?![A-Za-z0-9]) 而非 \b：C++/Node.js 这类符号结尾 token 后跟
# 标点时 \b 不成立，会整体失配。
_SKILL_RE = re.compile(
    r"\b(?:"
    r"(?i:python|golang|java|rust|sql|kubernetes|docker|k8s|react|vue|redis|kafka|nginx|mysql|git|linux|typescript|javascript)"
    r"|[A-Za-z][A-Za-z0-9]*[+#][+.#]*"
    r"|[A-Za-z]+(?:\.[A-Za-z0-9]+)+"
    r"|[A-Za-z]+\d[A-Za-z0-9]*"
    r"|[A-Z]{2,}[A-Za-z0-9]*"
    r"|[A-Z][a-z0-9]*[A-Z][A-Za-z0-9]*"
    r"|[a-z]+[A-Z][A-Za-z0-9]*"
    r")(?![A-Za-z0-9])"
)
_OVERLAP_THRESHOLD = 0.4


def _title_key(title: str) -> str:
    """title 归一化：去符号 + 去行业/级别后缀词，得到簇用关键词。"""
    t = _TITLE_SYMBOL_RE.sub("", str(title or ""))
    for stop in _TITLE_STOPWORDS:
        t = t.replace(stop, "")
    return t.strip() or (str(title or "").strip())


def _skills_of(job: Job) -> set[str]:
    """从岗位描述提取技能词集合（用于重叠率）。"""
    text = " ".join([job.title, job.description or "", " ".join(job.tags or [])])
    return set(m.group(0).lower() for m in _SKILL_RE.finditer(text))


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def cache_path() -> Path:
    """缓存文件路径：env TALENTFORGE_COMPETENCY_CACHE > 运行时 data/ 下。"""
    env = os.environ.get(CACHE_ENV)
    return Path(env) if env else RUNTIME_CACHE_PATH


class CompetencyClusterer(Protocol):
    """岗位胜任力聚类接口（预埋）：实现需满足——输入岗位 → 输出簇。"""

    def cluster(self, jobs: list[Job]) -> list[CompetencyCluster]:
        """把岗位集合聚成簇（簇内共享一个胜任力模型）。"""
        ...

    def find_cluster(self, job: Job) -> str | None:
        """新岗位命中已有簇返回簇 role_key，否则 None（需新建模型）。"""
        ...


class RuleCompetencyClusterer:
    """规则实现：title 关键词相等 或 技能词重叠 ≥ 阈值 → 同簇。"""

    # v2：技能词提取改大小写敏感的词形匹配（英文样板话术不再计入重叠率）
    version = "rule-v2"

    def __init__(self, overlap_threshold: float = _OVERLAP_THRESHOLD) -> None:
        self._threshold = overlap_threshold
        self._clusters: dict[str, list[Job]] = {}
        self._keys: dict[str, str] = {}  # job_id → role_key

    def _cluster_id(self, role_key: str) -> str:
        return hashlib.sha1(role_key.encode("utf-8")).hexdigest()[:10]

    def cluster(self, jobs: list[Job]) -> list[CompetencyCluster]:
        clusters: dict[str, dict] = {}  # role_key → {jobs, skills}
        for job in jobs:
            skills = _skills_of(job)
            best_key, best_overlap = None, 0.0
            for key, info in clusters.items():
                ov = _overlap(skills, info["skills"])
                if ov > best_overlap:
                    best_key, best_overlap = key, ov
            if best_key is not None and best_overlap >= self._threshold:
                clusters[best_key]["jobs"].append(job)
                clusters[best_key]["skills"] |= skills
            else:
                key = _title_key(job.title) or f"job-{job.id}"
                clusters.setdefault(key, {"jobs": [], "skills": set()})
                clusters[key]["jobs"].append(job)
                clusters[key]["skills"] |= skills
        result: list[CompetencyCluster] = []
        for role_key, info in clusters.items():
            member_ids = [j.id for j in info["jobs"]]
            result.append(
                CompetencyCluster(
                    cluster_id=self._cluster_id(role_key),
                    role_key=role_key,
                    member_job_ids=member_ids,
                    model=None,
                )
            )
            for jid in member_ids:
                self._keys[jid] = role_key
        return result

    def find_cluster(self, job: Job) -> str | None:
        return self._keys.get(job.id)


class CompetencyModelCache:
    """胜任力模型缓存：按 role_key 存取（data/competency_models.json）。

    文件头 _version 记写入时的 clusterer 版本；load 时版本不一致（含更早的
    无版本扁平格式）整体作废——换聚类算法后旧缓存自动失效重建。
    """

    VERSION_KEY = "_version"

    def __init__(self, path: Path | None = None, version: str | None = None) -> None:
        self._path = path or cache_path()
        self._version = version or RuleCompetencyClusterer.version
        self._models: dict[str, CompetencyModel] = {}

    def load(self) -> dict[str, CompetencyModel]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict) or data.get(self.VERSION_KEY) != self._version:
            return {}
        models: dict[str, CompetencyModel] = {}
        for key, raw in data.items():
            if key == self.VERSION_KEY or not isinstance(raw, dict):
                continue
            try:
                models[key] = CompetencyModel.model_validate(raw)
            except Exception:  # noqa: BLE001 — 单条损坏跳过，不拖垮整体
                continue
        self._models = models
        return models

    def get(self, role_key: str) -> CompetencyModel | None:
        return self._models.get(role_key)

    def put(self, model: CompetencyModel) -> None:
        self._models[model.role_key] = model
        self._persist()

    def _persist(self) -> None:
        payload: dict[str, object] = {self.VERSION_KEY: self._version}
        for k, v in self._models.items():
            payload[k] = v.model_dump()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
