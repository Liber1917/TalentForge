# M1 画像显式版 + 胜任力挂载 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development（本会话由 Sisyphus 编排，implementer 后台派发）。

**Goal:** O1 决议落地：八格结构位置 + α 假设机制（trial/archived）+ 词表 + 证据链 + overrides + LLM 基础层 + 简历 bootstrap ProfileEngine + TalentModel-skill 挂载（结构化 JSON）。

**Architecture:** 全部向后兼容扩展（M0 字段零改动）；LLM 层自研 httpx 单 provider；提示词遵守 prompt-cache 约定（system 静态）。

**Spec:** `docs/spec-m1-profile-competency.md`（源：O1 决议 D16–D19）。

## Global Constraints

- Python >=3.10；禁 LangChain；httpx 为唯一新依赖（ledger R2）
- M0 原字段零改动；新字段全部 default_factory/None
- 所有 LLM 调用测试走假实现；无真实 API key 落库
- system prompt 100% 静态（模块级常量），变量全在 user message
- conventional commit；每 task 一 commit；`GIT_MASTER=1` 前缀（controller 执行）

---

### Task 1: Schema 扩展（八格 + NarrativeClaim）

**Files:** Modify `talentforge/domain/profile.py`；Test `tests/test_schema_m1.py`
**Interfaces（Produces）:** `ClaimSource(kind,ref)`、`NarrativeClaim(text,state:trial|archived,evidence_count,confidence,sources)`、`SupportRelation/ExploitationRedline/ReproductionCosts/MobilityStatus`、`StructuralPosition` 新增 12 字段、`Profile.narrative_claims`

- [ ] Step 1 失败测试：

```python
from talentforge.domain.profile import (
    NarrativeClaim, ClaimSource, StructuralPosition, Profile,
    ExploitationRedline, ReproductionCosts, MobilityStatus, SupportRelation,
)

def test_narrative_claim_defaults():
    c = NarrativeClaim(text="偏好后端基础设施方向")
    assert c.state == "trial" and c.evidence_count == 0 and c.sources == []

def test_eight_grid_fields_present():
    sp = StructuralPosition(
        cash_buffer="约6个月",
        stage="在读·大三",
        support_network=[SupportRelation(kind="学长", note="可内推")],
        exploitation_redlines=[ExploitationRedline(kind="竞业限制", stance="never")],
        reproduction_costs=ReproductionCosts(housing="学校宿舍", skill_half_life_years=2.0),
        mobility=MobilityStatus(dare_bare_quit=False),
        reservation_wage=None,
    )
    assert sp.cash_buffer == "约6个月"
    assert sp.exploitation_redlines[0].stance == "never"

def test_backward_compat_profile_without_new_fields():
    p = Profile(name="张三")  # 不传 narrative_claims
    assert p.narrative_claims == []
    old = p.model_dump(); old.pop("narrative_claims")
    assert Profile.model_validate(old).name == "张三"  # 旧数据可加载
```

- [ ] Step 2 跑测确认失败 → Step 3 在 profile.py 追加（原字段不动）：

```python
from typing import Literal

class ClaimSource(BaseModel):
    """证据来源：简历段落/对话轮次/反馈事件/行为。"""
    kind: Literal["resume", "dialogue", "feedback", "behavior", "system"]
    ref: str = ""

class NarrativeClaim(BaseModel):
    """α 假设机制（O1/D16）：叙事主张，trial→（M3 用户确认）→active；M1 只有 trial/archived。"""
    text: str
    state: Literal["trial", "archived"] = "trial"
    evidence_count: int = 0
    confidence: float = 0.5
    sources: list[ClaimSource] = Field(default_factory=list)

class SupportRelation(BaseModel):
    kind: str = ""   # 导师/学长/家庭/内推人/朋友
    note: str = ""

class ExploitationRedline(BaseModel):
    kind: str = ""   # 996/大小周/on_call/无偿加班/竞业限制/培训违约金/加班费模糊
    stance: Literal["accept", "negotiable", "never"] = "negotiable"

class ReproductionCosts(BaseModel):
    housing: str = ""
    commute: str = ""
    food: str = ""
    skill_half_life_years: float | None = None

class MobilityStatus(BaseModel):
    dare_bare_quit: bool = False
    note: str = ""
```

StructuralPosition 追加字段（保留原 material_conditions/social_relations/extra）：

```python
    # —— 八格（O1 R3 / D17）：用户直填侧；市场侧(M2)入 market_assessment ——
    cash_buffer: Literal["≤3个月", "约6个月", "约1年", "≥2年"] | None = None
    stage: str = ""
    city_constraints: list[str] = Field(default_factory=list)
    family_duty: str = ""
    support_network: list[SupportRelation] = Field(default_factory=list)
    economic_independence: str = ""
    family_payback: bool = False
    reservation_wage: SalaryRange | None = None
    market_assessment: dict[str, Any] = Field(default_factory=dict)  # 系统估（M2，带证据标注）
    exploitation_redlines: list[ExploitationRedline] = Field(default_factory=list)
    reproduction_costs: ReproductionCosts | None = None
    mobility: MobilityStatus | None = None
```

Profile 追加：`narrative_claims: list[NarrativeClaim] = Field(default_factory=list)`

- [ ] Step 4 全测通过（含 M0 旧测试不破）→ Step 5 commit `feat: add eight-grid structural position and narrative claims schema`

---

### Task 2: 词表模块

**Files:** Create `talentforge/profile/__init__.py`（空）、`talentforge/profile/vocab.py`；Test `tests/test_vocab.py`
**Interfaces:** `VOCAB_VERSION:int`、`ATTRIBUTE_VOCAB:tuple`、`FALLBACK_ATTRIBUTE="其他"`、`resolve_attribute(raw:str)->str`

- [ ] Step 1 失败测试：

```python
from talentforge.profile.vocab import VOCAB_VERSION, ATTRIBUTE_VOCAB, resolve_attribute

def test_exact_match():
    assert resolve_attribute("薪资") == "薪资"
    assert resolve_attribute("  成长空间 ") == "成长空间"  # 去空白

def test_oov_falls_back():
    assert resolve_attribute("想要摸真东西") == "其他"
    assert resolve_attribute("") == "其他"

def test_versioned():
    assert isinstance(VOCAB_VERSION, int) and len(ATTRIBUTE_VOCAB) == 12
```

- [ ] Step 3 实现：

```python
"""效用轨属性闭集词表（O1/D18 护栏）。

规则：M1 只做精确匹配，认不出落「其他」桶；embedding 近邻归一 M2 挂。
词表替换必须经用户确认（D18）——规范词是用户查询/澄清自己档案的检索锚点。
"""
from __future__ import annotations

VOCAB_VERSION = 1

ATTRIBUTE_VOCAB: tuple[str, ...] = (
    "薪资", "技术栈", "工作模式", "成长空间", "稳定性", "城市",
    "公司类型", "行业", "团队", "加班文化", "福利保障", "氛围",
)
FALLBACK_ATTRIBUTE = "其他"


def resolve_attribute(raw: str) -> str:
    name = str(raw or "").strip()
    return name if name in ATTRIBUTE_VOCAB else FALLBACK_ATTRIBUTE
```

- [ ] Step 4 通过 → Step 5 commit `feat: add versioned attribute vocabulary with rule-based resolution`

---

### Task 3: LLM 基础层

**Files:** Modify `pyproject.toml`（dependencies 加 `"httpx>=0.27"`）；Create `talentforge/llm/__init__.py`（空）、`talentforge/llm/client.py`、`talentforge/llm/json_utils.py`；Test `tests/test_llm.py`
**Interfaces:** `LLMClient` Protocol（`async chat(system:str, user:str)->str`）、`EnvLLMClient`、`extract_json(text:str)->dict`

- [ ] Step 1 失败测试：

```python
import httpx
import pytest
from talentforge.llm.client import EnvLLMClient
from talentforge.llm.json_utils import extract_json

def _mock_client(payload: dict) -> EnvLLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    return EnvLLMClient(
        base_url="https://llm.test/v1", api_key="k", model="m",
        transport=httpx.MockTransport(handler),
    )

@pytest.mark.asyncio
async def test_chat_sends_static_system_and_dynamic_user():
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
    c = EnvLLMClient(base_url="https://l.test/v1", api_key="k", model="m",
                     transport=httpx.MockTransport(handler))
    out = await c.chat(system="STATIC", user="动态内容")
    assert out == "hi"
    msgs = seen["body"]["messages"]
    assert msgs[0] == {"role": "system", "content": "STATIC"}
    assert msgs[1]["role"] == "user"

def test_extract_json_direct():
    assert extract_json('{"a": 1}') == {"a": 1}

def test_extract_json_fenced():
    text = '说明如下\n```json\n{"dims": [1, 2]}\n```\n完'
    assert extract_json(text) == {"dims": [1, 2]}

def test_extract_json_wrapped():
    text = '结果是 {"x": "y"} 请查收'
    assert extract_json(text) == {"x": "y"}

def test_extract_json_garbage_raises():
    import pytest as _p
    with _p.raises(ValueError):
        extract_json("根本没有json")
```

- [ ] Step 3 实现 `client.py`：

```python
"""OpenAI 兼容单 provider 客户端（M1）。

约定（prompt-cache，仿 OpenBiliClaw）：system 必须是模块级静态常量，
一切变量放 user message——system 随调用变化会击穿 provider 缓存。
配置：TALENTFORGE_LLM_BASE_URL / TALENTFORGE_LLM_API_KEY / TALENTFORGE_LLM_MODEL。
"""
from __future__ import annotations

import os
from typing import Protocol

import httpx


class LLMClient(Protocol):
    async def chat(self, system: str, user: str) -> str: ...


class EnvLLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("TALENTFORGE_LLM_BASE_URL", "")).rstrip("/")
        self._api_key = api_key or os.environ.get("TALENTFORGE_LLM_API_KEY", "")
        self._model = model or os.environ.get("TALENTFORGE_LLM_MODEL", "")
        self._transport = transport
        self._timeout = timeout

    async def chat(self, system: str, user: str) -> str:
        if not self._base_url or not self._model:
            raise RuntimeError("LLM 未配置：需 TALENTFORGE_LLM_BASE_URL / TALENTFORGE_LLM_MODEL")
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        return str(data["choices"][0]["message"]["content"])
```

`json_utils.py`：

```python
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
```

- [ ] Step 4 通过（`pip install -e ".[dev]"` 重装以装 httpx）→ Step 5 commit `feat: add httpx LLM client with static-system convention and JSON tolerance`

---

### Task 4: ProfileEngine 默认实现（协议 async 化修正）

**Files:** Modify `talentforge/protocols.py`（`build_profile`/`update_from_feedback`/`Matcher.match`/`CompetencyModelBuilder.build` 改 `async def`）、`tests/test_protocols.py`（fake 同步→async）；Create `talentforge/profile/engine.py`；Test `tests/test_engine.py`

**Interfaces:** `DefaultProfileEngine(llm).build_profile(explicit:dict)->Profile`、`.update_from_feedback(profile,event)->Profile`

- [ ] Step 1 失败测试：

```python
import pytest
from talentforge.domain.feedback import FeedbackEvent
from talentforge.domain.decision import Verdict
from talentforge.profile.engine import DefaultProfileEngine, RESUME_BOOTSTRAP_SYSTEM_PROMPT

CANNED = """
{"identity": "后端基础设施倾向", "values": ["工程美学"], "deep_drives": ["把齿轮咬合讲清楚"],
 "cognitive_style": "原理型", "claims": [{"text": "偏好后端基础设施方向", "confidence": 0.7}]}
"""

class FakeLLM:
    async def chat(self, system: str, user: str) -> str:
        FakeLLM.seen = (system, user)
        return "```json\n" + CANNED + "\n```"

@pytest.mark.asyncio
async def test_build_profile_resume_bootstrap():
    eng = DefaultProfileEngine(llm=FakeLLM())
    p = await eng.build_profile({
        "name": "张三", "skills": ["Python"],
        "resume_text": "做过分布式存储课程项目…",
        "structural": {"cash_buffer": "约6个月",
                       "exploitation_redlines": [{"kind": "竞业限制", "stance": "never"}]},
        "utility_raw": [{"attribute": "薪资", "ordering": ["30k", "25k", "20k"]},
                        {"attribute": "想要摸真东西", "ordering": []}],
    })
    assert p.name == "张三"
    assert p.narrative.identity == "后端基础设施倾向"
    assert p.narrative_claims[0].state == "trial"
    assert p.narrative_claims[0].sources[0].kind == "resume"
    assert p.utility_preferences["薪资"].ordering[0] == "30k"
    assert p.utility_preferences["其他"].ordering == []          # OOV 归一
    assert "竞业限制" in p.deal_breakers                           # never→硬否决同步
    sysmsg, usermsg = FakeLLM.seen
    assert sysmsg == RESUME_BOOTSTRAP_SYSTEM_PROMPT and "分布式存储" in usermsg

@pytest.mark.asyncio
async def test_update_from_feedback_accumulates_evidence():
    eng = DefaultProfileEngine(llm=FakeLLM())
    p = await eng.build_profile({"name": "张三", "resume_text": "x"})
    ev = FeedbackEvent(job_id="j", decision_verdict=Verdict.APPLY,
                       dialogue_note="我确实更想做后端基础设施方向的工作")
    p2 = await eng.update_from_feedback(p, ev)
    assert p2.narrative_claims[0].evidence_count == 1
    assert p2.narrative_claims[0].sources[-1].kind == "feedback"
```

- [ ] Step 3 实现 `engine.py`（要点，完整代码在此文件）：

```python
"""简历 bootstrap + 隐式证据累积（O1/D16：显式优先、α 两态、对话即蒸馏）。"""
from __future__ import annotations

from typing import Any

from talentforge.domain.profile import (
    ClaimSource, NarrativeClaim, OrdinalPreference, Profile, SalaryRange, StructuralPosition,
)
from talentforge.domain.feedback import FeedbackEvent
from talentforge.llm.client import LLMClient
from talentforge.llm.json_utils import extract_json
from talentforge.profile.vocab import resolve_attribute

RESUME_BOOTSTRAP_SYSTEM_PROMPT = (
    "你是求职者画像构建器。根据用户消息中的简历文本，推断其人格叙事。"
    "只输出一个 JSON 对象，不要输出其他文字。格式："
    '{"identity": str, "values": [str], "deep_drives": [str], "cognitive_style": str,'
    ' "claims": [{"text": str, "confidence": float}]}。'
    "claims 是从简历可回溯的具体叙事主张（每条对应简历中的真实内容），不超过 8 条。"
)

_STRUCTURAL_KEYS = {
    "cash_buffer", "stage", "city_constraints", "family_duty", "economic_independence",
    "family_payback", "market_assessment",
}
_REDLINE_KEYS = {"kind", "stance"}


class DefaultProfileEngine:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def build_profile(self, explicit: dict[str, Any]) -> Profile:
        structural_raw = dict(explicit.get("structural") or {})
        redlines = [
            {"kind": r.get("kind", ""), "stance": r.get("stance", "negotiable")}
            for r in structural_raw.pop("exploitation_redlines", [])
        ]
        structural_raw["exploitation_redlines"] = redlines
        sp = StructuralPosition.model_validate(structural_raw)
        reservation = explicit.get("reservation_wage")
        if isinstance(reservation, dict):
            sp.reservation_wage = SalaryRange.model_validate(reservation)

        raw = await self._llm.chat(
            RESUME_BOOTSTRAP_SYSTEM_PROMPT,
            f"简历文本：\n{str(explicit.get('resume_text', ''))[:4000]}",
        )
        data = extract_json(raw)

        claims = [
            NarrativeClaim(
                text=str(c.get("text", "")).strip(),
                confidence=float(c.get("confidence", 0.5)),
                sources=[ClaimSource(kind="resume", ref="bootstrap")],
            )
            for c in data.get("claims", []) if str(c.get("text", "")).strip()
        ][:8]

        utility: dict[str, OrdinalPreference] = {}
        for item in explicit.get("utility_raw", []):
            attr = resolve_attribute(str(item.get("attribute", "")))
            utility[attr] = OrdinalPreference(
                attribute=attr, ordering=[str(x) for x in item.get("ordering", [])]
            )

        deal_breakers = [r["kind"] for r in redlines if r["stance"] == "never"]

        return Profile(
            name=str(explicit.get("name", "")),
            email=explicit.get("email"),
            years_experience=float(explicit.get("years_experience", 0.0)),
            skills=[str(s) for s in explicit.get("skills", [])],
            desired_roles=[str(r) for r in explicit.get("desired_roles", [])],
            preferred_locations=[str(x) for x in explicit.get("preferred_locations", [])],
            deal_breakers=deal_breakers,
            narrative={
                "identity": str(data.get("identity", "")),
                "values": [str(v) for v in data.get("values", [])],
                "deep_drives": [str(d) for d in data.get("deep_drives", [])],
                "cognitive_style": str(data.get("cognitive_style", "")) or None,
            },
            utility_preferences=utility,
            structural_position=sp,
            narrative_claims=claims,
        )

    async def update_from_feedback(self, profile: Profile, event: FeedbackEvent) -> Profile:
        note = f"{event.dialogue_note} {event.outcome or ''}"
        changed = False
        for claim in profile.narrative_claims:
            if claim.state != "trial" or not claim.text:
                continue
            key = claim.text[:8]
            if key and key in note:
                claim.evidence_count += 1
                claim.sources.append(ClaimSource(kind="feedback", ref=event.job_id))
                changed = True
        return profile if changed else profile.model_copy(deep=True)
```

protocols.py 修改（async 化四个方法）+ test_protocols.py 的 fake 改 async。

- [ ] Step 4 通过 → Step 5 commit `feat: default ProfileEngine (resume bootstrap, eight-grid, implicit evidence) + async protocols`

---

### Task 5: overrides 层

**Files:** Create `talentforge/profile/overrides.py`；Test `tests/test_overrides.py`
**Interfaces:** `load_overrides(path)->dict`、`save_overrides(path,d)`、`apply_overrides(profile,o)->Profile`（允许字段：skills/desired_roles/preferred_locations/deal_breakers/narrative）

```python
# 测试核心断言
def test_override_wins_and_rebuild_safe():
    p = Profile(name="张三", skills=["Python"])
    eff = apply_overrides(p, {"skills": ["Python", "Rust"]})
    assert eff.skills == ["Python", "Rust"] and p.skills == ["Python"]  # 原档不动
```

实现要点：`ALLOWED = {"skills","desired_roles","preferred_locations","deal_breakers","narrative"}`；`apply_overrides` 用 `profile.model_copy(update={k:v for k,v in o.items() if k in ALLOWED})`；save 用 `json.dumps(..., ensure_ascii=False, indent=2)`；load 容错返回 `{}`。
commit `feat: add profile overrides layer`

---

### Task 6: competency 挂载（TalentModel-skill 资产 + 结构化 Builder）

**Files:** bash 拷贝 `/home/TalentModel-skill/SKILL.md` 与 `references/*.md` → `talentforge/competency/assets/talent-model/`（附 `ATTRIBUTION.md` 注明来源与许可 MIT）；Create `talentforge/competency/__init__.py`、`talentforge/competency/builder.py`；Test `tests/test_competency.py`

`builder.py` 核心：

```python
COMPETENCY_SYSTEM_PROMPT = (
    "你是岗位胜任力建模器（方法源自 TalentModel-skill，见资产库）。"
    "硬规则：恰好 6 个一级维度；一级维度必须是人的稳定抽象特质，"
    "禁止技能/工具/技术栈/岗位职责（如 Python、系统设计、需求分析）；"
    "技能词降级到三级证据；校招/实习以潜力与可塑性为核心。"
    "只输出 JSON：{\"dimensions\":[{\"key\":\"D1\",\"name\":str,\"definition\":str,"
    "\"behaviors\":[str],\"evidence\":[str]}]}，每维度 behaviors≥2、evidence≥1。"
)

class DefaultCompetencyModelBuilder:
    def __init__(self, llm: LLMClient) -> None: ...
    async def build(self, role: str, level: str, jd_texts: list[str]) -> CompetencyModel:
        corpus = "\n---\n".join(t[:2000] for t in jd_texts)[:8000]
        raw = await self._llm.chat(COMPETENCY_SYSTEM_PROMPT, f"岗位：{role}\n级别：{level}\nJD材料：\n{corpus}")
        data = extract_json(raw)
        dims = [CompetencyDimension.model_validate(d) for d in data.get("dimensions", [])][:6]
        # 校验：维度名黑名单扫描（Python/Go/K8s/系统设计/需求分析/项目管理…命中即 ValueError）
        return CompetencyModel(role=role, level=level, dimensions=dims)
```

测试：FakeLLM 返回围栏 JSON → 6 维解析成功；返回含黑名单维度名的 JSON → `pytest.raises(ValueError)`。
commit `feat: mount TalentModel-skill assets and structured competency builder`

---

### Task 7: CLI 扩展

**Files:** Modify `talentforge/cli.py`；Test `tests/test_cli_m1.py`
**Interfaces:** `talentforge profile-build --name 张三 --resume-file <path> [--explicit-json <path>]`（输出 Profile JSON 摘要到 stdout）；`talentforge competency --role 后端工程师 --level 校招 --jd-file <path>`

实现要点：命令内 `asyncio.run(...)`；LLM 构造顺序——测试通过 `TALENTFORGE_LLM_BASE_URL` 环境变量 + monkeypatch `EnvLLMClient` 为 FakeLLM（注入函数放 cli 模块级 `_build_llm()` 便于 patch）；简历文件读文本传 engine。
测试：monkeypatch `talentforge.cli._build_llm` 返回 FakeLLM → CliRunner 断言 exit_code==0 且输出含 `"claims"` / 维度数。
commit `feat: add profile-build and competency CLI commands`

---

## 自审记录

- Spec 覆盖：spec-m1 §交付 1–7 ↔ Task 1–7；§不在本里程碑 均未越界。
- 无占位符；类型跨任务一致（NarrativeClaim/ClaimSource/engine 名与 Task 4 一致）。
- 风险：Task 4 改 protocols（async 化）——ledger R4 已裁决（M0 零消费者）。
