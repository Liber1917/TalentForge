# M11 规格 — 采集模式分级（manual / assist / auto）与最小任务子系统

> 决策依据：**D30**（修订 spec-m2b 排除项——任务派发从"不做"定向放宽为"仅 visit 原语、仅低风险平台、仅岗位类事实采集"）。D25 全部有效：服务器零浏览器、反爬强站唯一通道仍是扩展、绝不绕过验证码。

## 目标

按平台**风控强度 × 采集语义**给采集模式分档，替代"一律被动等待用户浏览"的单一口径：

- **Boss（强风控）**：升级为 assist——用户在场"主动浏览"，扩展提供页内拟人辅助（滚动脉冲加载更多），人启停；
- **B站/知乎（行为语义）**：维持 manual 被动 tap，**永不 auto**（红线，见"平台分档"）；
- **未来低风控岗位平台**：允许 auto——后台任务派发，扩展无人访问目标页采集岗位事实。

## 平台分档（policy）

| 平台 | 采集语义 | 风控 | 模式 | 依据 |
|---|---|---|---|---|
| zhipin (Boss) | 岗位事实 | 强（封禁史，D25 证据链） | **assist** | 用户裁决 + D25 |
| bilibili | 用户显示性行为 | 中 | **manual**（红线） | D6/O1：auto=伪造行为数据，污染画像认识论 |
| zhihu | 用户显示性行为 | 中 | **manual**（红线） | 同上 |
| **zhaopin 智联** | 岗位事实 | 中（浏览频控 40 次/10min ≫ 配额） | **auto** | m11-platform-recon §一；xixiluo95/AgentMesh 同构项目在维护 |
| **shixiseng 实习僧** | 岗位事实 | 弱—中（字体反爬为主，匿名可浏览） | **auto** | m11-platform-recon §二；无需登录态 |
| **liepin 猎聘** | 岗位事实 | 中—强（匿名降级+safe 验证） | **auto**（需登录态+人机协作） | m11-platform-recon §三；job-hunting 扩展存在证明 |
| lagou 拉勾 | 岗位事实 | — | **blocked**（禁入） | 平台 2026-05 破产（m11-platform-recon §四） |
| linkedin 领英 | 岗位事实 | 强 | **blocked**（禁入） | 合规硬伤×3 + 大陆不可达（m11-platform-recon §五） |

策略落地：`talentforge/sources/collection_policy.py` 内置默认表 + `data/collection_policy.json` 覆盖（gitignored，同 competency 缓存模式）。字段：`{platform: {mode, daily_quota, enabled}}`；`enabled:false` 或全局 `paused:true` = kill switch。

## 交付范围

### 1. 后端任务子系统

- `storage/db.py`：新增 `collection_tasks` 表
  （`id INTEGER PK / platform / url / status(pending|running|done|failed|aborted) / dwell_ms / claimed_at / finished_at / result_json / error`）
  + `enqueue_task`（同 platform+url 去重）、`claim_next_task`（单条原子 UPDATE ... WHERE status='pending'，防双_runner 重复领取）、`report_task`（done/failed/aborted + result/error 落库）。
- `api/routes_tasks.py`：
  - `POST /api/tasks/visit` `{platform, urls[]}` → enqueue；**非 auto 模式平台返回 403**（含红线平台与 assist 平台）；
  - `GET  /api/tasks/next?runner=<id>` → 原子 claim 一条 pending（无任务 204）；
  - `POST /api/tasks/{id}/report` `{status, inserted?, risk_signal?}` → 落库；`risk_signal` 非空 → 该平台写入冷却（policy 运行态，默认 30min）。
- `sources/collection_policy.py`：`mode_for(platform)` / `can_auto(platform)` / `quota_left(platform)` 纯函数 + JSON 覆盖加载。

### 2. 扩展任务执行器（auto 通道）

- `shared/task_client.ts`：claim/report 的 fetch 封装（对照 backend-endpoint.ts 模式）。
- `background/task_runner.ts`：独立 alarm（`talentforge-task`，默认 5min，复用现有 alarms 机制）→
  GET next → `chrome.tabs.create({active:false})` → 停留 `dwell_ms`（服务端下发，含拟人抖动，上限 30s）→ 关 tab → POST report。
  平台 content script 若已注册（岗位类适配器），页面加载即按现有机制采集入库（Boss 的 wapi/DOM 双通道模式平移）——task_runner 只管生命周期，不管采集细节。
  页面加载失败/超时 → report failed；检测到风控关键词（captcha/verify/security-check，title+body 扫描）→ report aborted + risk_signal。
- `manifest.json`：+`tabs` 权限（后台 tab 生命周期管理）；auto 平台接入时再补对应 `host_permissions`/content script。

### 3. Boss 主动浏览辅助（assist）

`content/boss.ts` 增浮动开关"辅助浏览"（仅搜索页注入）：
- 开启后按拟人间隔（1.2–2.4s 随机抖动）执行 `scrollBy` 脉冲直至页底或用户关闭；现有 scroll 监听自然触发 wapi/DOM 收获，**采集语义与人手动滚动完全一致**；
- 会话内有效（不持久化），页内即可启停——"人在场"由用户亲自开关保证；
- 纯函数化脉冲调度器（next delay/步长/是否到底）独立导出，vitest 覆盖。

### 4. 护栏（全部在 policy/任务参数内强制）

- 单任务停留上限 30s；并发 tab = 1（runner 串行）；平台日配额默认 20 任务；
- 风控信号 → 中止 + 平台冷却 30min（冷却期内 enqueue 直接 403）+ 事件落库（设置页展示，M11 不加 notifications 权限）；
- kill switch：policy `paused:true` 或单平台 `enabled:false`；
- **绝不绕过验证码/风控**（D25 红线不变）。

## 架构（auto 数据流）

```
设置页/policy (data/collection_policy.json)
        │ 平台分档 + 配额 + 冷却
        ▼
POST /api/tasks/visit ──► collection_tasks(SQLite, pending)
        │ (仅 auto 平台可入队)
        ▼
扩展 service-worker: alarm(5min) ──► GET /api/tasks/next ──原子claim──► running
        │
        ▼
tabs.create(active:false, url) ──► 平台 content script 现有机制采集 ──► POST /api/jobs/batch（不变）
        │ dwell_ms（拟人抖动）
        ▼
tab close ──► POST /api/tasks/{id}/report ──► done / failed / aborted(+risk_signal→冷却)
```

## 排除项（M11 不做）

- 验证码/风控**对抗**（检测→中止冷却；绕过=红线）
- 多账号、指纹伪装、代理池
- 复杂动作编排（点击序列/自动翻页动作链）、backfill 子系统、WS 推送（沿 alarms 轮询）
- B站/知乎任何形式的 auto（**语义红线**，D30③——不是风控权衡，是数据正确性）
- OpenBiliClaw task multiplex 全套

## 验收

1. **单元/契约**：pytest（policy 纯函数含红线平台拒绝、任务 enqueue 幃等/原子 claim/状态机、routes 契约含 403 路径）+ vitest（task_runner 状态机 fake-chrome 全路径、assist 脉冲调度器、task_client）全绿，现有用例零回归。✅（2026-09-03：pytest 391 绿、vitest 99 绿、web 130 绿、ruff 触达文件零告警）
2. **离线 E2E**：TestClient 构造 mock auto 平台 → enqueue → claim → report(done) 全链；对 bilibili/zhipin enqueue → 403。✅（tests/test_collection_tasks.py 路由契约组）
3. **Boss assist 真机**（手动验收单）：开关开启 → 页面以拟人节奏持续加载 → 岗位持续入库（jobs 表 scraped_at 递增）→ 关闭即停。⏳ pending-user（用户真机执行；脉冲调度器与开关逻辑已 vitest 覆盖）
4. **auto 真机**：按 m11-platform-recon 分档结论执行——智联（首）+ 实习僧（次）真机验收；猎聘带登录态作第三目标；拉勾/领英 blocked 拒绝路径。✅（2026-09-03 扩展真机 E2E：真 Chromium 加载 dist 扩展 + 真 uvicorn 后端——实习僧真实站点 20 卡入库、智联 mock 域 fe-api hook 桥接入库、bilibili enqueue 403、blocked 平台拒绝路径测试通过；猎聘登录态目标留待真用户环境，脚本存档 `.omo/ulw-research/20260901-001011/e2e_extension.cjs`）
5. **实施期新增发现（已修复并纳入验收）**：① Chromium 151 起 content-script 直连 127.0.0.1 被 PNA 拦截且 SW fetch 带 `chrome-extension://` Origin——岗位上报统一改 service worker 中转（`shared/jobs_report.ts`），Origin 校验为扩展来源+摄入端点（events/jobs/tasks）放行（app.py，tests 覆盖），该修复同时挽救 boss.ts 主线在新 Chrome 上的既有风险；② inline `<script>` 注入被页面 CSP 拦截——智联 MAIN-world 改 manifest `"world": "MAIN"` 声明式注入（FF 需 128+）。

## 风险声明

auto 档是对 D25"零对抗"的定向弱化：自动化访问模式本身就是平台风控的检测对象。本 spec 的立场是把 auto 限制在"低防御目标 × 岗位事实语义 × 硬预算"内，双红线（Boss、行为类平台）不动摇——**账号安全 > 采集覆盖**。
