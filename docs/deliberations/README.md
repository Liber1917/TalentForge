# TalentForge 研讨流程（TF-Deliberation）

> 适配自 Rust RFC（FCP/模板纪律）、Python PEP（Provisional 状态）、德尔菲法（RAND 指南：匿名/受控反馈/预定义共识/轮次上限）、Amazon 评审（静默阅读/强者后言）。两方对话 + 子代理独立评审的混合制。

## 触发门槛（分级豁免）

**进流程**：跨模块影响 / 逆转代价高 / 理论开放（O1、O2 级）。**不进流程**：小决策聊天定 + `design-decisions.md` 记一行。

## 工件

每问题一份 `docs/deliberations/O<N>-<slug>.md`，状态机：

```
draft → 研讨中(R1/R2) → FCP → accepted | rejected | deferred | provisional
```

- 决裁人：用户。作者：Sisyphus。
- **Drawbacks 必须写在建议之前**（Rust 纪律：先反驳自己）。
- **未决分歧显式保留**（德尔菲原则：分歧是合法产出，不得为收敛而掩盖）。
- accepted 后工件不可改；推翻走 supersede（新编号+链接）。
- **provisional**：允许先实现，跑一段时间后必须回来定 Final。

## 轮次（上限 3 轮 + FCP）

```
R0  作者成文：Context/Drivers/Options(≥3)/Drawbacks——不写结论倾向
R1  独立匿名评审：3-5 视角子代理，互相不可见，只回传聚合表（受控反馈）；
    作者综合意见最后写（强者后言）
R2  决裁人研讨：用户读聚合表后对话，质疑/追问/改选项
FCP 用户宣告 disposition；新实质论点 → 退回 R2；
    轮次达上限仍分歧 → 分歧按原样写入决议，可 provisional
```

## 视角面板

- **常规问题**：3 视角，全部 flash 子代理（后台并行）。
- **理论密度高**（O1 级）：5 视角，**≥3 个由主会话（主模型）承担**，其余 flash 子代理。
  - 主模型视角在主会话内逐视角独立评审（先写完所有视角再综合，防自我锚定）；
  - flash 子代理视角后台并行，与主模型视角互不可见。
- 视角按问题定制，示例（O1）：信号密度 / 工程成本 / 理论严谨 / 产品价值 / 契约稳定性。

## 模型路由现实约束

子代理派发仅后台可用；`task()` 无法指定模型。主模型评审由主会话承担，flash 评审由 `explore`/`general` 子代理承担（实测模型见 `design-decisions.md` 模型决议）。

## 与 SDD 衔接

决议 → 回写 `design-decisions.md`（D 编号）→ 必要时更新 spec → 才允许进对应里程碑 plan。触发条件未到的问题维持 deferred。
