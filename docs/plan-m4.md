# M4 实施计划 — 反馈闭环（feedback/）

> 上游：`docs/spec-m4-feedback.md`（已用户确认方向）。
> 执行方式：SDD，逐任务派发后台 general 子代理，controller 审查 + commit。
> 现状基线：pytest 150 + web node:test 68 全绿；`talentforge/feedback/` 为空壳。

## 任务分解

### Task 1: 域模型扩展 + 回流规则引擎（纯后端核心）

**Files:** Modify `talentforge/domain/feedback.py`（job_title/action 字段）、`talentforge/domain/profile.py`（OrdinalPreference.evidence）；Create `talentforge/feedback/engine.py`（FeedbackPipeline）、`talentforge/feedback/store.py`（JSON 追加式存储）；Test `tests/test_feedback.py`

**Interfaces:**
- `FeedbackEvent` 微扩（见 spec §1.1，默认值兼容）
- `OrdinalPreference.evidence: list[str] = []`
- `feedback/store.py`：`FeedbackStore(path)` — `append(event) -> list[FeedbackEvent]`（幂等：同 job_id+action 更新）、`recent(limit) -> list[FeedbackEvent]`、`summary() -> dict`
- `feedback/engine.py`：`FeedbackPipeline.apply(profile, event) -> Profile`（纯函数式，不修改入参）：
  - 偏好回流规则表（spec §1.3：apply+offer/interview 升 1 位 / skip+note 注释 / decided 打 evidence 标注；单事件单步防抖）
  - 叙事修正：复用 `DefaultProfileEngine.update_from_feedback` 的 claim 证据累积语义（trial claim note 命中 → evidence_count+1）——以纯函数形式移植其匹配逻辑，或注入 engine 调用，选侵入最小方案
- salary/tech_stack 段位定位：从 Job 数据（list_jobs 或事件内嵌 title/salary 文本）推导段位 key——回流函数签名接收可选 job: Job | None，无 job 时跳过段位定位只做叙事修正

**要点:** 全部规则版无 LLM；偏好只动 ordering 与 evidence，绝不改 narrative；深拷贝入参。
commit: `feat: feedback pipeline with revealed-preference rules`

### Task 2: API 路由 + 联调

**Files:** Create `talentforge/api/routes_feedback.py`；Modify `talentforge/api/app.py`（挂载）；Test `tests/test_api_feedback.py`

**Interfaces:**
- `POST /api/feedback/events`：body=FeedbackEvent JSON → store.append + pipeline.apply（profile 写回）→ 返回 `{ok, event, preference_changes: [...]}`（changes 列出本次动了哪些 ordering）
- `GET /api/feedback/events?limit=50` → `{events: [...]}`
- `GET /api/feedback/summary` → `{n_decided, n_apply, n_hold, n_skip, n_outcome, n_preference_changes}`
- profile 路径复用 `api/common.py` 的 load/save（TALENTFORGE_PROFILE_PATH）；feedback log 路径 `data/feedback_log.json`（env TALENTFORGE_FEEDBACK_LOG 覆盖，模块级变量可 monkeypatch）

**要点:** 与 chat/claims 路由风格一致；测试注入 tmp 路径；原 150 测试不回归。
commit: `feat: feedback API routes`

### Task 3: 工作台反馈按钮 + 画像 evidence 显示（Web）

**Files:** Modify `web/js/views/jobs.js`（详情面板三按钮 + 回流徽章）、`web/js/views/profile.js`（效用轨 evidence 小字）；Test `web/tests/jobs.test.mjs`、`web/tests/profile.test.mjs` 追加断言

**Interfaces:**
- 详情面板底部 `feedback-actions` 行：**我已投递 / 我跳过了 / 记录结果** 三按钮（btn--ghost 小号，primary 色留给系统建议）
  - 已投递/跳过 → POST feedback（真 fetch，不走 fixtures base，参照 sources.js 的 no-store 模式）→ 徽章"已记录：投递 08-22"替换按钮行
  - 记录结果 → 原地展开四个小按钮（面试中/已拒/offer/无回音）→ POST outcome
- fixtures 模式：本地 mock（同 chat.js 模式——按钮点击后本地状态更新 + 徽章显示，不真调后端）；?real=1 真调
- 画像效用轨：ordering 后缀 `（含 N 次决策回流）` 小字（evidence 数组长度 > 0 时）

**要点:** renderJobDetail 纯函数追加 feedbackRow（输入 job + feedbackState）；XSS 转义照旧；node:test 断言按钮/徽章/evidence 小字。
commit: `feat: workbench feedback buttons and preference evidence display`

### Task 4: 端到端验收 + 收尾

**Files:** Create `docs/research/m4-acceptance.md`；Modify `README.md`（反馈闭环使用节）

**要点:** 真后端实测 spec §5.4 端到端场景（记录投递+offer → profile salary ordering evidence 变化）；全测绿；验收笔记（含限制：规则版保守回流/段位定位依赖 Job 数据/无自动检测）。
commit: `docs: M4 feedback acceptance notes`

---

## 自审记录

- Spec 覆盖：§1↔T1、§2↔T2、§3↔T3、§5↔T4。§4 范围外未越界（无自动检测/无 LLM 偏好建议/无多画像）。
- 依赖：T1→T2→T3→T4 串行（T2 依赖 T1 管线，T3 依赖 T2 端点契约，T4 全链路）。
- 已知风险：ordering 段位定位需 salary 文本→段位 key 映射（"25-50K·16薪"→"30-40万"）——T1 用宽松映射（K→万换算落段），失配时跳过段位只做叙事修正，不阻塞回流。
- feedback/ 从空壳升级为稳定核心模块——补齐 D15 的第二半（decision/ 已在 M0/M2a 交付）。
