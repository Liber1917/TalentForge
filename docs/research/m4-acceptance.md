# M4 验收笔记 — 反馈闭环（显示性偏好回流 + 叙事修正）

> 验收依据：`docs/spec-m4-feedback.md` §5（验收口径）；`docs/plan-m4.md` Task 4。
> 验收日期：2026-08-22。执行人：agentic worker（Task 4）。
> 结论速览：**单元/API/Web/端到端四层全过（§1–§4）；画像效用轨实测回流生效（§5）。规则版保守回流无 LLM 参与偏好（D18 边界），feedback/ 从空壳补齐为 D15 稳定核心模块。**

---

## 1. 单元测试（回流规则逐条）

`tests/test_feedback.py` 22 项全绿：

- FeedbackStore：append 幂等（同 job_id+action 更新不重复）、recent 倒序、summary 计数、文件损坏容错（坏 JSON 告警按空表）
- FeedbackPipeline 规则表：
  - decided apply → 段位 evidence 追加，ordering 不动
  - outcome offer → 段位 **+1 位**（向更优方向；已在最前不动位仍记 evidence）
  - skip+note → 只 evidence 注释（截断 40 字），ordering 不动
  - 段位未命中（薪资超出全区间）→ 跳过段位，叙事修正照常
  - 叙事修正：note 前8/后8字符命中 trial claim → evidence_count+1（语义同 DefaultProfileEngine）
  - 纯函数性：apply 不改入参（model_copy deep）；旧 profile 无 evidence 字段兼容

## 2. API 测试（9 项全绿）

`tests/test_api_feedback.py`：POST decided 落段 evidence + profile 写回 / 幂等二次 POST 只一条 / outcome offer 升位 / job 不在库不 500 / 画像缺失空兜底 / 叙事修正 / 非法 body 422 / events 倒序 limit / summary 计数。

## 3. Web 测试（6 项新增，74 全绿）

`web/tests/jobs.test.mjs` +5：未记录态三按钮 + outcome 四按钮隐藏 / 已记录徽章"已记录：投递 08-22" + 改按钮 / renderJobDetail 联动 / XSS（title 与 verdict 转义）/ fmtDay。
`web/tests/profile.test.mjs` +1：效用轨"（含 N 次决策回流）"小字（空数组/缺字段不显示）。

## 4. 端到端实测（真后端，spec §5.4 场景）

环境：uvicorn + TALENTFORGE_PROFILE_PATH=/tmp e2e 画像 + seed 观澜数据岗（30-35万/年，落"30-40万"段位）。

| 步骤 | 结果 |
|---|---|
| POST decided apply | ✅ `evidence +1: 2026-08-22 apply 数据平台后端工程师(30-35万/年)`，ordering 不动 |
| POST outcome offer | ✅ `salary ordering: '30-40万' +1 位（offer）` + evidence +1；ordering 变为 `['30-40万','40万以上','20-30万']` |
| 同 job+action 重复 POST | ✅ 幂等（decided 事件数保持 1） |
| GET /api/feedback/summary | ✅ 计数正确 |
| 浏览器真模式（?real=1） | ✅ 工作台详情"我已投递"→ 真 POST → 徽章"已记录：投递 08-22"+改按钮 |
| 画像效用轨 | ✅ 显示 `薪资 30-40万›40万以上›20-30万（含 4 次决策回流）`——段位升位与回流计数均可见 |

## 5. 限制说明（明确范围，不视为缺陷）

| 限制 | 说明 |
|---|---|
| 规则版保守回流 | 无 LLM 参与偏好（D18 人机边界）；单事件单步防抖，偏好只动 ordering 与 evidence，绝不改 narrative |
| summary 无 n_preference_changes | 无存储数据源不虚构；可从 profile 各 evidence 条目数近似，暂不实现（deviation 已注） |
| 段位定位依赖 Job 数据 | job 不在库/薪资缺失/未命中区间时跳过段位操作只做叙事修正 |
| 无自动检测投递 | 用户手动记录（尊重决策人身份，spec §4 范围外） |
| 回流只覆盖薪资属性 | tech_stack 段位回流留待 M5（当前岗位数据 tags 无结构化技术栈段位） |

## 6. 全量测试基线

- Python pytest：**181 passed**（T1 +22、T2 +9，原 150 无回归）
- Web node:test：**74 passed**（T3 +6，原 68 无回归）
