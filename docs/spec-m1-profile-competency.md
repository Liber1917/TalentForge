# M1 规格 — 画像显式版 + 胜任力挂载

> 依据：spec-mvp-design.md §10 + O1 决议（D16–D19）。本文件只转录已决事项，不引入新决策；实现级裁决见 plan-m1 ledger。

## 交付范围

1. **Schema 扩展（向后兼容）**：`NarrativeClaim`（α 假设机制：trial/archived 两态 + 证据链）、八格 `StructuralPosition` 字段、`Profile.narrative_claims` 可选附加字段。M0 原字段零改动。
2. **词表模块**：效用轨属性闭集（中文 12 项 + "其他"），规则式精确匹配（embedding 兜底后置 M2），`VOCAB_VERSION` 常量；词表迁移须用户确认（D18，本里程碑只落版本常量与替换确认的接口形状）。
3. **LLM 基础层**：httpx 单 provider 客户端（env 配置 base_url/api_key/model）、结构化 JSON 容错（fenced/wrapper）、prompt-cache 约定（system 静态、变量进 user）。
4. **ProfileEngine 默认实现**：`build_profile`（简历 bootstrap：显式表单直填八格 + LLM 单跳推断叙事轨→trial 态 claims，各带 source；效用轨显式偏好经词表归一）；`update_from_feedback`（隐式证据累积：反馈与 claims 的关键词匹配 → evidence_count+1，不调 LLM）。"绝不"级剥削红线同步进 `Profile.deal_breakers`。
5. **overrides 层**：独立 JSON 文件，读时叠加（用户编辑优先），画像重建不覆盖。
6. **competency 挂载**：TalentModel-skill 资产拷贝入库（SKILL.md + references，注明出处）+ `DefaultCompetencyModelBuilder`（LLM 产结构化 6 维 JSON；提示词编码硬规则：一级维度=抽象特质非技能、校招潜力优先、技术词降级证据层）。
7. **CLI**：`profile-build` / `competency` 两命令；测试全用假 LLM，真实调用待用户 API key。

## 不在本里程碑

- 内容采集（8 平台插件）→ M2（与岗位源同属采集机械）
- 证据话语五要素 → M3 反思对话提示词设计
- 格 5/8 市场侧估算 → M2 岗位数据到位后
- 词表 embedding 归一 → M2

## 测试策略

Schema 向后兼容测试（旧 JSON 无新字段可加载）；词表解析测试；JSON 容错测试；假 LLM 注入的 engine/builder 测试；prompt system 静态性测试（两次调用字节一致，仿 OpenBiliClaw 测试）。
