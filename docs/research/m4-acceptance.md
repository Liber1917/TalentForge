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

---

## D25 补充验收 — Boss 扩展采集闭环（2026-08-23）

> 依据：D25 决策（扩展采集为反爬平台唯一通道）。诊断遥测（/api/debug + [TF-DEBUG] 日志）**保留**——排查期产物转为常驻观测点。

### 排查实录（三次断点，全部实证定位）

1. **ES import 致 content script 从未执行**：vite 单配置共享 chunk，产物带 `import{...}`——Chrome content script 是经典脚本，注入即 SyntaxError（网页 console 才可见，而被反调试关闭，故长期无声失败；M2b 的 B站/知乎采集同病）。修复：`scripts/build-extension.mjs` 每入口独立 IIFE 构建（service worker 保持 ES module）。
2. **URL 判断疑云**：用户实际 URL `/web/geek/jobs`（复数）——`includes('/web/geek/job')` 子串匹配本就覆盖，非问题；真正断点靠遥测排除。
3. **wapi 字段名错位**：实测 `joblist.json` 主键为 `encryptJobId`（无 `jobId`/`brandName`），30 条全被映射过滤。修复：映射按 `encryptJobId` + `skills` 并入 tags + `jobExperience/jobDegree/bossName` 组合为 description。

### 验收结果（真机，用户浏览器）

| 步骤 | 结果 |
|---|---|
| 重装扩展 + 刷新 `/web/geek/jobs?query=agent&city=101020100` | ✅ 遥测 `[TF-DEBUG] wapi-body code:0 listLen:30` |
| wapi → 映射 → POST /api/jobs/batch | ✅ 200，一次入库 30 条 |
| 数据质量 | ✅ 真实公司（乐鑫/TapTap/九方云等）、明文薪资自动换算年薪（45-90万等）、地点/技能标签齐全 |
| 去重 | ✅ 重复刷新不重复入库（URL 主键） |
| 工作台消费 | ✅ `?real=1#/jobs` 可筛选浏览 |

### 已知边界

- 列表接口无公司名字段（boss 视角卡片），company 暂缺——详情页补全留待后续（点击进详情时 job_detail 页可采）
- 只采第一页（page=1, pageSize=30）；翻页采集待用户实际翻页行为驱动（scroll 触发的 DOM 通道在 SPA 虚拟列表下 cards=0，暂以 wapi 为主通道）
- `__zp_stoken__` 有效期内 wapi 可用；过期后需刷新页面让页面 JS 重算（正常浏览天然满足）

### 操作说明（用户视角）

装扩展 → 正常登录并浏览 Boss 搜索页（任意关键词/城市）→ 数据自动入库 → 工作台查看。**筛选/换城市/换关键词都支持**：搜索 URL 的 query/city 参数被 content script 解析后按当前条件调 wapi——你搜什么就采什么。
