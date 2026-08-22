# M4 规格 — 反馈闭环（显示性偏好回流 + 叙事修正）

> 状态：待用户复核。上游：`docs/spec-mvp-design.md` §3.2（feedback/ 为稳定核心锁定模块）、D5（反馈闭环）、D11（反思对话）。
> 本文补齐 MVP spec 的 feedback/ 缺口：M0–M3 已交付画像/岗位/决策/Web，但用户的三元决策行为没有回流，画像不会越用越准。

## 0. 问题

现在的断点：工作台给出 投/观望/不投 → **用户的实际选择无人记录** →
`utility_preferences` 永远停留在初始值 → 下次匹配仍用旧偏好。

闭环后：用户每记录一次决策行为 → 偏好序按显示性偏好（revealed preference）微调 →
画像随使用变准。这是 MVP spec 对 feedback/ 的定义："显示性偏好回流 + 叙事修正"。

## 1. 数据模型（扩展现有，不新建表）

### 1.1 FeedbackEvent（已有，微扩）

`talentforge/domain/feedback.py` 已有：

```python
job_id / decision_verdict / outcome / dialogue_note / at
```

微扩两个字段（默认值兼容旧数据）：

- `job_title: str = ""` — 展示用（回流条目列表要显示岗位名，不必反查库）
- `action: Literal["decided", "outcome"] = "decided"` — 区分"用户记录了决策"与"用户补报了结果"

### 1.2 feedback_log（新增 JSON 文件，与 profile.json 同级）

```json
{"events": [
  {"job_id": "...", "job_title": "Python 后端工程师", "decision_verdict": "hold",
   "action": "decided", "outcome": null, "dialogue_note": "", "at": "..."}
]}
```

- 路径 `data/feedback_log.json`（`data/` 已 gitignore；env `TALENTFORGE_FEEDBACK_LOG` 可覆盖）
- 追加式（append-only），幂等键 `job_id + action`：同岗位重复记录决策 → 更新 verdict 不重复追加

### 1.3 偏好回流的落点：utility_preferences 的 ordering 微调

显示性偏好的保守提取（规则版，无 LLM 参与——LLM 不改偏好，人机边界 D18 同源）：

| 用户行为 | 规则 |
|---|---|
| verdict=apply 且后续 outcome=offer/interview | 该岗位的 tech_stack/salary 段位在对应 ordering 中 **+1 位**（升） |
| verdict=skip 且 dialogue_note 非空 | note 命中的偏好属性 ordering 中命中间 **降权注释**（只在 evidence 记录，不动序） |
| 任何 decided 事件 | 该岗位的 salary 段位在 salary ordering 中标注"已在此段位行动"（evidence 计数） |

- 每条 ordering 最多同时动 1 位/事件（防抖：单事件不大幅改序）
- `OrdinalPreference` 增加可选 `evidence: list[str]`（默认空，兼容旧 profile）记录回流依据，如 `"2026-08-22 hold 星辰科技(25-50K·16薪)"`

### 1.4 叙事修正（已有能力的接线）

`engine.update_from_feedback` 已实现 trial claim 证据累积（note 命中 → evidence_count+1）。
M4 只需在回流管线中调用它一次（同一事件同时驱动偏好回流 + 叙事修正）。

## 2. API 面

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/feedback/events` | POST | 记录决策/结果（body: FeedbackEvent JSON），驱动回流管线 |
| `/api/feedback/events` | GET | 最近回流条目（limit=50） |
| `/api/feedback/summary` | GET | 统计（决策数/apply-hold-skip 分布/outcome 分布/偏好调整次数） |

## 3. Web 落点（工作台）

- 决策卡详情面板底部新增一行：**"我已投递 / 我跳过了 / 记录结果"** 三个轻量按钮
  - 点"我已投递" → POST `{job_id, decision_verdict: "apply", action: "decided"}`（用户真实行为覆盖系统建议——这是显示性偏好的本源）
  - 点"我跳过了" → 同理 verdict=skip
  - 点"记录结果" → 小弹出（面试中/已拒/offer/无回音）→ POST `{action: "outcome"}`
- 已记录的岗位：详情面板显示回流徽章（"已记录：投递 08-22"），按钮变为可改状态
- 画像页效用轨：ordering 旁若有 evidence 显示小字"含 N 次决策回流"

## 4. 范围外

- 自动检测投递行为（邮件/网站事件）——不做，用户手动记录是尊重决策人身份
- LLM 生成偏好调整建议——不做，规则版保守回流；LLM 只在叙事修正的 claim 归纳侧（已有）
- 多画像实例（同 MVP spec）

## 5. 验收口径

1. 单元：回流规则表逐条测试（apply+offer → 升序 / skip+note → 注释 / 防抖单事件单步）
2. API：POST/GET/summary 契约 + 幂等（同 job 同 action 二次 POST 更新不重复）
3. Web：三按钮 → 状态徽章 → 画像效用轨 evidence 显示（node:test 断言 + 浏览器实测）
4. 端到端：记录"投递 观澜数据(30-45K)" + "offer" → GET /api/profile 的 salary ordering 中 30-40万段位 evidence +1 且位置不动或 +1 位
