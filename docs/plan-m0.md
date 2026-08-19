# M0 骨架 + 稳定契约 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 TalentForge 的项目骨架 + 稳定契约（数据模型 schema + 可拓展外围 Protocol + 决策象限纯函数）+ 端到端空壳 CLI。

**Architecture:** 稳定核心（decision 象限判定）先锁死为纯函数，可拓展外围（profile/competency/field/sources/matcher）以 Protocol 定义接口、MVP 空实现。数据模型（Pydantic schema）是两者之间的稳定契约。

**Tech Stack:** Python 3.10+（环境 3.10.12，无 uv，用 pip）、pydantic v2、click、pytest + pytest-asyncio、ruff、mypy。

**Spec:** `docs/spec-mvp-design.md`（§3 模块、§5 数据模型、§6.1 决策判定、§10 M0、§12 技术栈）。本计划从 spec 出发，执行者须同时读 spec。

## Global Constraints

（复制自 spec，每条任务隐式遵守）

- Python `>=3.10`（spec 写 3.11+，环境 3.10.12，M0 语法兼容 3.10）
- 不用 LangChain/LangGraph（自研轻量管线）
- 数据本地 SQLite、无遥测、无云
- 单人本地工具
- 稳定核心 decision/feedback 不设扩展接口；外围 profile/competency/field/sources/matcher 必须 Protocol 化（D15）
- 偏好用序数（非基数 0–100）；O2 量化方法待定，Match 的 fit 用 `FitLevel` 枚举占位
- 每个决策可回溯：可解释链含 画像证据 × 胜任力维度 × JD 原文（M0 只建 schema 骨架）
- 只读采集、验证码暂停等人工、不绕过反爬、不自动投递（MVP）
- 类型注解全部函数；ruff（line-length=100, select E/F/I/UP/B）；mypy；pytest；conventional commit（feat/fix/refactor/docs/test/chore）

---

### Task 1: 项目骨架

**Files:**
- Create: `pyproject.toml`
- Create: `talentforge/__init__.py`
- Create: `talentforge/domain/__init__.py`（空）
- Create: `talentforge/decision/__init__.py`（空）
- Create: `talentforge/feedback/__init__.py`（空）
- Create: `talentforge/storage/__init__.py`（空）
- Create: `tests/__init__.py`（空）

**Interfaces:**
- Produces: 包 `talentforge` 可 import；`talentforge.__version__` 存在；pytest 可运行。

- [ ] **Step 1: 写 pyproject.toml**

```toml
[build-system]
requires = ["hatchling>=1.24.2"]
build-backend = "hatchling.build"

[project]
name = "talentforge"
version = "0.1.0"
description = "TalentForge — 锻造人才的求职决策助手"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "pydantic>=2.7",
    "click>=8.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.9",
    "mypy>=1.15",
]

[project.scripts]
talentforge = "talentforge.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["talentforge"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.10"
```

- [ ] **Step 2: 写 `talentforge/__init__.py`**

```python
"""TalentForge — 锻造人才的求职决策助手。"""

__version__ = "0.1.0"
```

- [ ] **Step 3: 建空包目录** — `talentforge/domain/__init__.py`、`talentforge/decision/__init__.py`、`talentforge/feedback/__init__.py`、`talentforge/storage/__init__.py`、`tests/__init__.py` 均为空文件。

- [ ] **Step 4: 安装并验证**

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q          # 期望：0 collected（无测试），exit 0
python -c "import talentforge; print(talentforge.__version__)"
```

- [ ] **Step 5: Commit**（提交前与用户确认）

```bash
git add pyproject.toml talentforge/ tests/
git commit -m "chore: scaffold talentforge package skeleton"
```

---

### Task 2: 数据模型 schema（稳定契约）

**Files:**
- Create: `talentforge/domain/profile.py`
- Create: `talentforge/domain/field.py`
- Create: `talentforge/domain/job.py`
- Create: `talentforge/domain/competency.py`
- Create: `talentforge/domain/match.py`
- Create: `talentforge/domain/decision.py`
- Create: `talentforge/domain/feedback.py`
- Modify: `talentforge/domain/__init__.py`（re-export）
- Test: `tests/test_domain.py`

**Interfaces:**
- Produces（后续任务依赖的类型）：
  - `Profile`（含 `narrative: NarrativeIdentity`、`utility_preferences: dict[str, OrdinalPreference]`、`structural_position: StructuralPosition`、`revealed_preferences: list[RevealedChoice]`）
  - `FieldModel`（含 `risks: list[StructuralRisk]`）
  - `Job`（含 `risk_keys: list[str]`）
  - `CompetencyModel`（含 `dimensions: list[CompetencyDimension]`）
  - `Match`（含 `market_fit: FitLevel|None`、`growth_fit: FitLevel|None`、`structural: StructuralAssessment`）
  - `Decision`（含 `verdict: Verdict`、`explainable_chain: list[ExplainableLink]`、`reflective_question: str|None`）
  - `FeedbackEvent`（含 `job_id: str`、`decision_verdict: Verdict`、`outcome: str|None`）

- [ ] **Step 1: 写失败测试 `tests/test_domain.py`**

```python
from talentforge.domain.profile import Profile, NarrativeIdentity, OrdinalPreference
from talentforge.domain.match import Match, FitLevel, StructuralAssessment
from talentforge.domain.decision import Decision, Verdict, ExplainableLink
from talentforge.domain.job import Job


def test_profile_defaults_and_dual_track():
    p = Profile(name="张三", skills=["Python"])
    assert p.narrative.identity == ""
    assert p.utility_preferences == {}
    assert p.revealed_preferences == []
    p.utility_preferences["work_mode"] = OrdinalPreference(
        attribute="work_mode", ordering=["remote", "hybrid", "onsite"]
    )
    assert p.utility_preferences["work_mode"].ordering[0] == "remote"


def test_match_fit_is_ordinal_enum():
    m = Match(job_id="j1", market_fit=FitLevel.HIGH, growth_fit=FitLevel.LOW)
    assert m.market_fit == FitLevel.HIGH
    assert m.structural.risks == []


def test_decision_explainable_chain_and_reflective_question():
    d = Decision(
        job_id="j1",
        verdict=Verdict.HOLD,
        explainable_chain=[
            ExplainableLink(
                dimension="D1",
                profile_evidence="简历有分布式项目",
                jd_text="要求高并发经验",
                assessment="部分匹配",
            )
        ],
        reflective_question="你连续三次都投了大小周岗位，优先级变了吗？",
    )
    assert d.reflective_question is not None
    assert len(d.explainable_chain) == 1


def test_job_has_structural_risk_keys():
    j = Job(source="boss", title="后端", company="X", location="深圳", url="https://x", risk_keys=["996"])
    assert "996" in j.risk_keys
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_domain.py -v
# 期望：FAIL — ModuleNotFoundError: talentforge.domain.profile
```

- [ ] **Step 3: 写实现**（逐文件）

`talentforge/domain/profile.py`：

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SalaryRange(BaseModel):
    min_annual: int | None = Field(default=None, ge=0)
    max_annual: int | None = Field(default=None, ge=0)
    currency: str = "CNY"


class NarrativeIdentity(BaseModel):
    """人格叙事轨：自然语言为主，结构化字段待研究扩展。"""

    identity: str = ""
    values: list[str] = Field(default_factory=list)
    deep_drives: list[str] = Field(default_factory=list)
    cognitive_style: str | None = None


class StructuralPosition(BaseModel):
    """结构位置（D12）：研究阶段，自然语言 + 可扩展。"""

    material_conditions: str = ""
    social_relations: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class RevealedChoice(BaseModel):
    """显示性偏好（D6/O2）：投/拒/接offer 行为流。"""

    job_id: str
    choice: str  # applied | rejected | passed | offer_accepted | offer_rejected
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""


class OrdinalPreference(BaseModel):
    """岗位属性偏好序（序数，非基数）。"""

    attribute: str  # salary | tech_stack | work_mode | growth | stability | location | company_type
    ordering: list[str] = Field(default_factory=list)  # 偏好从高到低


class Profile(BaseModel):
    """求职者画像：显式层 + 双轨 + 结构位置。"""

    name: str
    email: str | None = None
    years_experience: float = 0.0
    skills: list[str] = Field(default_factory=list)
    desired_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    salary_expectation: SalaryRange | None = None
    deal_breakers: list[str] = Field(default_factory=list)
    narrative: NarrativeIdentity = Field(default_factory=NarrativeIdentity)
    utility_preferences: dict[str, OrdinalPreference] = Field(default_factory=dict)
    structural_position: StructuralPosition = Field(default_factory=StructuralPosition)
    revealed_preferences: list[RevealedChoice] = Field(default_factory=list)
```

`talentforge/domain/field.py`：

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StructuralRisk(BaseModel):
    """结构性风险信号（D12/D14）：每个带政治经济学解释。"""

    key: str  # 996 | 大小周 | 无社保 | 无偿加班 | 竞业限制 | ...
    label: str
    why: str  # 为什么这是剥削（政治经济学解释）
    severity: str = "warning"  # warning | deal_breaker


class FieldModel(BaseModel):
    """场域建模（劳动力市场政治经济学）。研究阶段，可扩展。"""

    industry: str = ""
    industry_analysis: str = ""
    risks: list[StructuralRisk] = Field(default_factory=list)
    ideology_signals: list[str] = Field(default_factory=list)  # 「996是福报」等
    extra: dict[str, Any] = Field(default_factory=dict)
```

`talentforge/domain/job.py`：

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from talentforge.domain.profile import SalaryRange


class Job(BaseModel):
    """归一化岗位（扩展 jobclaw Job 模型 + 结构字段）。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str  # boss
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    salary: SalaryRange | None = None
    tags: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    company_type: str | None = None
    industry: str | None = None
    work_mode: str | None = None  # remote | onsite | hybrid
    risk_keys: list[str] = Field(default_factory=list)  # 命中场域风险，如 ["996"]
    metadata: dict[str, Any] = Field(default_factory=dict)
```

`talentforge/domain/competency.py`：

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class CompetencyDimension(BaseModel):
    """胜任力维度（一级）：抽象特质，非技能（TalentModel-skill 约束）。"""

    key: str  # D1..D6
    name: str  # 认知复杂度 / 内驱与主动闭环 / ...
    definition: str
    behaviors: list[str] = Field(default_factory=list)  # 二级：可观察行为
    evidence: list[str] = Field(default_factory=list)  # 三级：证据


class CompetencyModel(BaseModel):
    """岗位胜任力框架（结构化 JSON，非仅 HTML，O2 前置）。"""

    role: str
    level: str  # 校招 | 实习 | 应届 | 社招
    dimensions: list[CompetencyDimension] = Field(default_factory=list)  # 6 个
    candidate_evidence: dict[str, list[str]] = Field(default_factory=dict)  # dimension_key -> evidence
```

`talentforge/domain/match.py`：

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FitLevel(str, Enum):
    """序数契合等级（O2 量化方法待定，MVP 用高/低占位）。"""

    HIGH = "high"
    LOW = "low"


class StructuralAssessment(BaseModel):
    """结构认知（第三维，作为调制项，§6.1）。"""

    risks: list[str] = Field(default_factory=list)  # 命中的 risk key
    notes: list[str] = Field(default_factory=list)  # 政治经济学警示


class Match(BaseModel):
    """三维匹配结果（市场契合 × 成长契合 × 结构认知）。"""

    job_id: str
    market_fit: FitLevel | None = None
    growth_fit: FitLevel | None = None
    structural: StructuralAssessment = Field(default_factory=StructuralAssessment)
    reasoning: list[str] = Field(default_factory=list)
    matched_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)
```

`talentforge/domain/decision.py`：

```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    APPLY = "apply"  # 投
    HOLD = "hold"  # 观望
    SKIP = "skip"  # 不投


class ExplainableLink(BaseModel):
    """可解释链一环：画像证据 × 胜任力维度 × JD 原文。"""

    dimension: str
    profile_evidence: str
    jd_text: str
    assessment: str  # 匹配 | 差距 | 缺失


class Decision(BaseModel):
    """三元决策 + 可解释链 + 差距/补短板 + 结构性追问。"""

    job_id: str
    verdict: Verdict
    reason: str = ""
    explainable_chain: list[ExplainableLink] = Field(default_factory=list)
    gap: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)
    structural_reflection: list[str] = Field(default_factory=list)
    reflective_question: str | None = None  # 反思性对话钩子（D11）
```

`talentforge/domain/feedback.py`：

```python
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from talentforge.domain.decision import Verdict


class FeedbackEvent(BaseModel):
    """反馈事件（闭环回流，D5/D11）。"""

    job_id: str
    decision_verdict: Verdict
    outcome: str | None = None  # interview | rejected | offer | no_response
    dialogue_note: str = ""  # 对话自述（叙事修正）
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

`talentforge/domain/__init__.py`：

```python
from talentforge.domain.profile import (
    NarrativeIdentity, OrdinalPreference, Profile, RevealedChoice, SalaryRange, StructuralPosition,
)
from talentforge.domain.field import FieldModel, StructuralRisk
from talentforge.domain.job import Job
from talentforge.domain.competency import CompetencyDimension, CompetencyModel
from talentforge.domain.match import FitLevel, Match, StructuralAssessment
from talentforge.domain.decision import Decision, ExplainableLink, Verdict
from talentforge.domain.feedback import FeedbackEvent

__all__ = [
    "CompetencyDimension", "CompetencyModel",
    "Decision", "ExplainableLink", "FeedbackEvent", "FieldModel",
    "FitLevel", "Job", "Match", "NarrativeIdentity", "OrdinalPreference",
    "Profile", "RevealedChoice", "SalaryRange", "StructuralAssessment",
    "StructuralPosition", "StructuralRisk", "Verdict",
]
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_domain.py -v   # 期望：4 passed
```

- [ ] **Step 5: Commit**

```bash
git add talentforge/domain/ tests/test_domain.py
git commit -m "feat: add stable-contract domain models (Profile/Field/Job/Competency/Match/Decision/Feedback)"
```

---

### Task 3: 决策象限判定（稳定核心纯函数）

**Files:**
- Create: `talentforge/decision/verdict.py`
- Modify: `talentforge/decision/__init__.py`（re-export）
- Test: `tests/test_verdict.py`

**Interfaces:**
- Consumes: `Match`、`Verdict`、`FitLevel`、`StructuralAssessment`（Task 2）
- Produces: `decide(match: Match, deal_breakers: list[str]) -> Verdict`（后续 Task 5 CLI 依赖）

- [ ] **Step 1: 写失败测试 `tests/test_verdict.py`**

```python
import pytest

from talentforge.domain.match import Match, FitLevel, StructuralAssessment
from talentforge.domain.decision import Verdict
from talentforge.decision.verdict import decide


def _match(mf, gf, risks=None):
    return Match(
        job_id="j",
        market_fit=mf,
        growth_fit=gf,
        structural=StructuralAssessment(risks=risks or []),
    )


def test_high_high_applies():
    assert decide(_match(FitLevel.HIGH, FitLevel.HIGH), []) == Verdict.APPLY


def test_high_low_is_hold_comfort_zone():
    assert decide(_match(FitLevel.HIGH, FitLevel.LOW), []) == Verdict.HOLD


def test_low_high_is_hold_challenge():
    assert decide(_match(FitLevel.LOW, FitLevel.HIGH), []) == Verdict.HOLD


def test_low_low_skips():
    assert decide(_match(FitLevel.LOW, FitLevel.LOW), []) == Verdict.SKIP


def test_deal_breaker_skips():
    assert decide(_match(FitLevel.HIGH, FitLevel.HIGH, risks=["996"]), ["996"]) == Verdict.SKIP


def test_structural_risk_downgrades_apply_to_hold():
    assert decide(_match(FitLevel.HIGH, FitLevel.HIGH, risks=["无社保"]), []) == Verdict.HOLD


def test_missing_fit_skips():
    assert decide(_match(None, FitLevel.HIGH), []) == Verdict.SKIP
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_verdict.py -v
# 期望：FAIL — ModuleNotFoundError: talentforge.decision.verdict
```

- [ ] **Step 3: 写实现 `talentforge/decision/verdict.py`**

```python
from __future__ import annotations

from talentforge.domain.match import Match, FitLevel
from talentforge.domain.decision import Verdict


def decide(match: Match, deal_breakers: list[str]) -> Verdict:
    """二维象限 + 结构调制（spec §6.1）。

    二维象限：
      市场契合高 × 成长契合高 → apply
      市场契合高 × 成长契合低 → hold（舒适区）
      市场契合低 × 成长契合高 → hold（挑战型机会，交反思对话升级）
      市场契合低 × 成长契合低 → skip
    结构调制：
      命中 deal-breaker → skip（硬边界）
      存在结构性风险（未触 deal-breaker）→ 最高 hold（不投，先观望）
      缺失 fit → skip（评估不完整，不轻率决策）
    """
    risks = match.structural.risks
    hard = [r for r in risks if r in deal_breakers]
    if hard:
        return Verdict.SKIP

    mf, gf = match.market_fit, match.growth_fit
    if mf is None or gf is None:
        return Verdict.SKIP

    base = _quadrant(mf, gf)
    if risks and base == Verdict.APPLY:
        return Verdict.HOLD  # 结构性风险调制：有风险不投，先观望
    return base


def _quadrant(mf: FitLevel, gf: FitLevel) -> Verdict:
    if mf == FitLevel.HIGH and gf == FitLevel.HIGH:
        return Verdict.APPLY
    if mf == FitLevel.HIGH and gf == FitLevel.LOW:
        return Verdict.HOLD
    if mf == FitLevel.LOW and gf == FitLevel.HIGH:
        return Verdict.HOLD
    return Verdict.SKIP
```

`talentforge/decision/__init__.py`：

```python
from talentforge.decision.verdict import decide

__all__ = ["decide"]
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_verdict.py -v   # 期望：7 passed
```

- [ ] **Step 5: Commit**

```bash
git add talentforge/decision/ tests/test_verdict.py
git commit -m "feat: add decision quadrant rule with structural modulation"
```

---

### Task 4: Protocol 定义（可拓展外围接口）

**Files:**
- Create: `talentforge/protocols.py`
- Test: `tests/test_protocols.py`

**Interfaces:**
- Consumes: Task 2 的 domain 类型
- Produces（后续里程碑的默认实现都要满足）：
  - `ProfileEngine`：`build_profile(explicit: dict) -> Profile`；`update_from_feedback(profile, event) -> Profile`
  - `CompetencyModelBuilder`：`build(role, level, jd_texts) -> CompetencyModel`
  - `FieldModeler`：`analyze(industry, company) -> FieldModel`
  - `Matcher`：`match(profile, job, competency, field) -> Match`
  - `SourceAdapter`：`source: str`；`async scrape_jobs(query, limit) -> list[Job]`

- [ ] **Step 1: 写失败测试 `tests/test_protocols.py`**

```python
from talentforge.protocols import ProfileEngine, Matcher, SourceAdapter
from talentforge.domain.profile import Profile
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.job import Job


class _FakeProfileEngine:
    def build_profile(self, explicit: dict) -> Profile:
        return Profile(name=explicit["name"])

    def update_from_feedback(self, profile: Profile, event: FeedbackEvent) -> Profile:
        return profile


def test_profile_engine_is_structurally_satisfied():
    engine = _FakeProfileEngine()
    assert isinstance(engine, ProfileEngine)
    p = engine.build_profile({"name": "张三"})
    assert p.name == "张三"


class _FakeSource:
    source = "boss"

    async def scrape_jobs(self, query: str, limit: int = 20) -> list[Job]:
        return []


def test_source_adapter_protocol_attr():
    adapter = _FakeSource()
    assert isinstance(adapter, SourceAdapter)
    assert adapter.source == "boss"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_protocols.py -v
# 期望：FAIL — ModuleNotFoundError: talentforge.protocols
```

- [ ] **Step 3: 写实现 `talentforge/protocols.py`**

```python
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from talentforge.domain.profile import Profile
from talentforge.domain.field import FieldModel
from talentforge.domain.job import Job
from talentforge.domain.competency import CompetencyModel
from talentforge.domain.match import Match
from talentforge.domain.feedback import FeedbackEvent


@runtime_checkable
class ProfileEngine(Protocol):
    """画像引擎（可拓展外围，O1 待定深度）。"""

    def build_profile(self, explicit: dict[str, Any]) -> Profile: ...

    def update_from_feedback(self, profile: Profile, event: FeedbackEvent) -> Profile: ...


@runtime_checkable
class CompetencyModelBuilder(Protocol):
    """胜任力建模（可拓展外围，O2 待理论审视）。"""

    def build(self, role: str, level: str, jd_texts: list[str]) -> CompetencyModel: ...


@runtime_checkable
class FieldModeler(Protocol):
    """场域建模（可拓展外围，全新无上游）。"""

    def analyze(self, industry: str, company: str) -> FieldModel: ...


@runtime_checkable
class Matcher(Protocol):
    """三维匹配（可拓展外围，O2 量化方法待定）。"""

    def match(
        self, profile: Profile, job: Job, competency: CompetencyModel, field: FieldModel
    ) -> Match: ...


@runtime_checkable
class SourceAdapter(Protocol):
    """岗位源适配器（可拓展外围，MVP=Boss 单源）。"""

    source: str

    async def scrape_jobs(self, query: str, limit: int = 20) -> list[Job]: ...
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_protocols.py -v   # 期望：2 passed
```

- [ ] **Step 5: Commit**

```bash
git add talentforge/protocols.py tests/test_protocols.py
git commit -m "feat: define extensible-periphery protocols (ProfileEngine/Competency/Field/Matcher/Source)"
```

---

### Task 5: 端到端空壳 CLI（walking skeleton）

**Files:**
- Create: `talentforge/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `decide`（Task 3）、`Match`/`FitLevel`/`StructuralAssessment`/`Verdict`（Task 2）
- Produces: CLI 入口 `talentforge`（`talentforge.cli:main`），命令 `decide`——给定匹配信号输出三元决策。

- [ ] **Step 1: 写失败测试 `tests/test_cli.py`**

```python
from click.testing import CliRunner

from talentforge.cli import main


def test_decide_command_end_to_end():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["decide", "--market-fit", "high", "--growth-fit", "high"],
    )
    assert result.exit_code == 0
    assert "apply" in result.output


def test_decide_command_with_risk():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["decide", "--market-fit", "high", "--growth-fit", "high", "--risk", "无社保"],
    )
    assert result.exit_code == 0
    assert "hold" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_cli.py -v
# 期望：FAIL — ModuleNotFoundError: talentforge.cli
```

- [ ] **Step 3: 写实现 `talentforge/cli.py`**

```python
from __future__ import annotations

import click

from talentforge.decision.verdict import decide
from talentforge.domain.match import Match, FitLevel, StructuralAssessment


@click.group()
def main() -> None:
    """TalentForge — 锻造人才的求职决策助手。"""


@main.command("decide")
@click.option("--market-fit", type=click.Choice(["high", "low"]), required=True)
@click.option("--growth-fit", type=click.Choice(["high", "low"]), required=True)
@click.option("--risk", multiple=True, help="命中的结构性风险，如 996、无社保")
@click.option("--deal-breaker", multiple=True, help="用户 deal-breaker，命中即不投")
def decide_command(market_fit: str, growth_fit: str, risk: tuple[str, ...], deal_breaker: tuple[str, ...]) -> None:
    """M0 walking skeleton：给定匹配信号，输出三元决策。"""
    match = Match(
        job_id="demo",
        market_fit=FitLevel(market_fit),
        growth_fit=FitLevel(growth_fit),
        structural=StructuralAssessment(risks=list(risk)),
    )
    verdict = decide(match, list(deal_breaker))
    click.echo(f"verdict={verdict.value}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试 + 手动冒烟确认通过**

```bash
pytest tests/test_cli.py -v   # 期望：2 passed
talentforge decide --market-fit high --growth-fit high              # 期望输出：verdict=apply
talentforge decide --market-fit high --growth-fit high --risk 无社保  # 期望输出：verdict=hold
talentforge decide --market-fit low --growth-fit low                # 期望输出：verdict=skip
```

- [ ] **Step 5: Commit**

```bash
git add talentforge/cli.py tests/test_cli.py
git commit -m "feat: add walking-skeleton CLI (decide command)"
```

---

## 自审记录

- **Spec 覆盖**：§3.1 模块（Task 1 骨架 + Task 4 协议 + Task 3 决策核心）、§5 数据模型（Task 2）、§6.1 决策判定（Task 3）、§10 M0（全部 5 task）、D15 稳定核心+可拓展外围（Task 3 核心锁定 + Task 4 外围 Protocol）。无缺口。
- **占位符**：无 TBD/TODO。所有 step 含实际代码。
- **类型一致性**：`decide`、`Match`、`Verdict`、`FitLevel`、`StructuralAssessment` 在 Task 2/3/5 中命名一致；Protocol 方法签名（`build_profile`/`match`/`scrape_jobs` 等）在 Task 4 定义、后续里程碑复用。
- **环境适配**：Python 3.10（`from __future__ import annotations` 保证 `X | None` 兼容）；无 uv 用 pip + venv。

## 已知遗留（非 M0 范围）

- O1（画像层深度）、O2（量化方法）仍悬置，触发时机见 spec §11。M0 的 `FitLevel` 枚举是 O2 的占位，后续可替换为序数偏好比较而不破坏 decision 核心（D15 验证）。
