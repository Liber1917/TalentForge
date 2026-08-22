# M3 Web 界面 实施计划

> **For agentic workers:** superpowers:subagent-driven-development（Sisyphus 编排，后台派发，controller 审查 + git-master 提交）。

**Goal:** FastAPI 后端 + 纯 vanilla JS 三视图 Web（对话/工作台/画像），DESIGN.md 视觉系统全落地，离线假数据可演示，接真实后端。

**Spec:** `docs/spec-m3-web.md`。视觉：`web/DESIGN.md`。

## Global Constraints

- Python 3.10+；新增依赖 fastapi+uvicorn（M3 升级 stdlib events_server）；前端纯 vanilla JS 无框架
- 三视图 SPA：`#chat`（对话首页）/ `#jobs`（决策工作台）/ `#profile`（画像面板），hash 路由
- 视觉 token 全引用 DESIGN.md（无裸 hex）；无 emoji 图标（用 SVG/文本符号）
- 对话流卡片契约（DecisionCard/ClaimCard/RiskNote/ReflectivePrompt）严格按 spec-m3-web §1
- 离线可演示：假数据 JSON 驱动全卡片渲染；真后端接上后切换
- 后端 /api/events（插件采集）保留；新增 /api/chat /api/claims /api/jobs /api/report /api/profile
- conventional commit；GIT_MASTER=1；每 task 一 commit；node_modules/dist gitignored

---

### Task 1: FastAPI 升级 + 静态服务骨架

**Files:** Modify `pyproject.toml`（+fastapi uvicorn）、`talentforge/api/`（events.py 保留，新增 main.py/app.py）；Test `tests/test_api_app.py`

**Interfaces:** `create_app() -> FastAPI`：挂 /api/events（迁移 M2b events_server 的 handle_events 逻辑为 FastAPI 路由）、静态挂载 /web /m 占位、健康检查 /api/health、CORS。CLI `talentforge serve-api`（替代原 stdlib server，保留 events_server 兼容）。

**要点：** FastAPI app 工厂模式；events 端点保持幂等契约（复用 handle_events 纯函数）；静态目录 `web/`（当前只有 DESIGN.md，Task 3 填页面）。测试：TestClient 验证 /api/health、/api/events POST 幂等、静态根。
commit: `feat: FastAPI app factory with events endpoint and static mount`

### Task 2: 假数据 seed + 卡片 JSON 契约落地

**Files:** Create `talentforge/api/fixtures.py`、`talentforge/api/schemas.py`（Pydantic 卡片模型）；Test `tests/test_fixtures.py`

**Interfaces:** `get_fixture_chat() / get_fixture_jobs() / get_fixture_profile()`（返回 spec §1 卡片契约 JSON——DecisionCard/ClaimCard/RiskNote/ReflectivePrompt 全类型样例）；`CardJSON` Pydantic 模型（type 判别联合）。种子数据含：5 条对话（含 2 DecisionCard + 1 ClaimCard + 1 RiskNote）、8 岗位、完整 Profile（三轨+待定池 3 条+八格）。
**要点：** 假数据是前端开发契约——字段名/类型与 spec §1 完全一致；Profile 从 docs/demo/profile.json（已含 6 trial claims）读入补全。
commit: `feat: fixture data and card JSON schemas`

### Task 3: 静态 Web 骨架 + 设计系统 CSS

**Files:** Create `web/index.html`、`web/css/tokens.css`、`web/css/base.css`、`web/css/components.css`、`web/js/router.js`、`web/js/api.js`；Test：构建/语法校验（node --check 或简单脚本）

**Interfaces:** hash 路由三视图；`tokens.css` 从 DESIGN.md §2/§3 提取 CSS 变量（--surface-primary 等全 token，无裸 hex）；`api.js` 封装 fetch（base /api，开发期可切 /api/fixtures 假数据）。
**要点：** 本任务只做骨架+设计系统 CSS 落地+路由+API 层（页面内容 Task 4-6 填）。Primitive Showcase 先行：Card/Btn/VerdictBadge/ClaimCard/EvidenceChain 五原语的 showcase.html（375/768/1280 响应式验证，DESIGN.md §5 门）。
commit: `feat: web skeleton with design-system tokens and hash router`

### Task 4: 对话首页（#chat）

**Files:** Create `web/js/views/chat.js`、`web/partials/chat.html`；Modify `web/js/router.js`；Test：渲染假数据断言

**Interfaces:** 渲染聊天流（ChatBubble user/assistant）+ 内嵌卡片（DecisionCard/ClaimCard/RiskNote/ReflectivePrompt 各自渲染函数）；Composer 输入→POST /api/chat/turns（假数据模式本地 mock 响应）；卡片操作（claim confirm/reject → 调端点 + 局部更新）。
**要点：** 卡片渲染严格按 DESIGN.md 原语；EvidenceChain 展开/收起（details 语义）；ReflectivePrompt 内嵌输入框。
commit: `feat: chat view with card rendering`

### Task 5: 决策工作台（#jobs）

**Files:** Create `web/js/views/jobs.js`、`web/partials/jobs.html`；Test：渲染/筛选断言

**Interfaces:** 岗位列表（VerdictBadge 前置）+ 详情面板（理由链 EvidenceChain + RiskNote 展开 + ReflectivePrompt 跳对话 + gap/补短板）；搜索/城市/verdict 筛选；"生成报告"按钮→POST /api/report/run→轮询状态。假数据模式：列表过滤本地完成。
commit: `feat: jobs view with list-detail layout`

### Task 6: 画像面板（#profile）

**Files:** Create `web/js/views/profile.js`、`web/partials/profile.html`；Test：渲染断言

**Interfaces:** 待定池 tab（ClaimCard 列表 + 操作）+ 叙事/效用/结构位置 tab；八格卡片网格（D17）；简历校对流（resume-review 的抽取文本 diff 视图）；导出 JSON 按钮。
commit: `feat: profile view with tabs and eight-grid`

### Task 7: 后端真实端点 + 联调

**Files:** Create `talentforge/api/routes_chat.py`、`routes_claims.py`、`routes_jobs.py`、`routes_report.py`、`routes_profile.py`；Modify `talentforge/api/app.py`；Test `tests/test_api_routes.py`

**Interfaces:** 按 spec §5 实现真实端点（复用 M1/M2a/M2b 组件：ProfileUpdatePipeline/DefaultProfileEngine/generate_report/field.assess/CoarseMatcher/storage）；前端从假数据切换真 API（api.js 环境开关）。意图路由：chat POST 解析→自由对话（LLM）/触发决策（跑报告管线）/画像确认。
**要点：** 对话意图路由是 M3 核心复杂度——minimal 版：关键词路由（"投/看看/岗位/工作"→决策，"简历/我/觉得/想"→对话），后续可换 LLM 意图分类。
commit: `feat: real API routes wired to core components`

### Task 8: 联调验收 + 收尾

**Files:** Create `docs/research/m3-acceptance.md`；Modify `README.md`；Test：全测

**要点：** 离线假数据演示验收（可复现，记录截图级描述）；真后端联调（fake LLM 环境）验收三视图数据流；真实 LLM pending-user。视觉验收：Primitive Showcase 三断点（375/768/1280）逐原语过——用 Playwright 截图断言（若环境可用）或人工清单。README M3 使用节。
commit: `docs: M3 acceptance + README usage`

---

## 自审记录

- Spec 覆盖：spec-m3-web §1↔T4、§2↔T5、§3↔T6、§4/§5↔T7、§7验收↔T8、技术形态↔T1-3。范围外（WebSocket/暗色/移动深优）未越界。
- 依赖顺序：T1→T2→T3（骨架/CSS/路由）→T4/5/6（三视图，依赖 T3 可并行但串行派发）→T7（真后端）→T8。
- 已知风险：vanilla JS 无框架下三视图状态同步（claim 操作两页刷新）——实现用简单事件总线（window CustomEvent）；FastAPI 与 M2b stdlib server 并存冲突——serve-api 切换，events_server 保留兼容。
- 新增依赖 fastapi/uvicorn（M3 正式 API 面，spec 已定）。
