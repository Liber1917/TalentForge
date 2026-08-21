# M2b 插件内容采集（B站+知乎）最小闭环 实施计划

> **For agentic workers:** superpowers:subagent-driven-development（Sisyphus 编排，后台派发，controller 审查 + git-master 提交）。

**Goal:** 用户浏览 B站/知乎 → 插件只读采集 → 事件入库 → α 待定池信号累积，验证"画像自长"链路。

**Spec:** `docs/spec-m2b-extension.md`。侦察依据：`docs/research/m2-extension-recon.md`。

## Global Constraints

- Python >=3.10（后端）；Node 18+ / TypeScript（插件，工具链新增）
- 插件只读被动采集：不写操作、不抓验证码、无任务系统
- 事件契约：BehaviorEvent{event_id, type, url, title, timestamp, source_platform, context{pageType, domSnapshot?, viewport, scrollPosition}, metadata}；event_id 幂等
- LLM 走既有 EnvLLMClient；prompt 静态 system 约定
- 新增依赖：无 Python 新依赖（fastapi 已由 M0/M1 环境隐含？——**需确认**：TalentForge 至今无 FastAPI！后端 API 是 M3 范围。本里程碑的 /api/events 用**最小方案：stdlib http.server 单端点**还是引入 FastAPI？——见 Task 1 裁决）
- conventional commit；GIT_MASTER=1；每 task 一 commit

---

### Task 1: 后端事件接收（最小 API）

**Files:** Create `talentforge/api/__init__.py`(空)、`talentforge/api/events.py`；Modify `talentforge/storage/db.py`（加 events 表）；Test `tests/test_events_api.py`

**裁决点（controller 已定）**: 不引 FastAPI（M3 才做正式 Web/API 面）。用 **stdlib `http.server` 的线程 HTTP 服务器**实现 `POST /api/events` 单端点，绑定 127.0.0.1:8420——够插件对接、零新依赖、M3 换 FastAPI 时接口契约不变。

**Interfaces:**
- `handle_events(payload: dict, conn: sqlite3.Connection) -> dict`（纯函数，可测）：payload={"events":[{...}]}；每事件校验 event_id(1-400 字符)/type/url/source_platform，缺失即返回 {"ok":false,"rejected":[event_id...]}；有效事件 INSERT OR IGNORE（event_id PK）进 events 表；返回 {"ok":true,"accepted":n,"duplicates":m}
- `events_server(host="127.0.0.1", port=8420) -> ThreadingHTTPServer`：注册 /api/events POST 路由（body JSON → handle_events → 响应 {"ok":true} 或 400）
- db.py 加 events 表：event_id TEXT PK, event_type TEXT, url TEXT, title TEXT, source_platform TEXT, context_json TEXT, metadata_json TEXT, received_at TEXT ISO

**测试：** handle_events 幂等（同 event_id 二次→duplicates+1）；缺 event_id→rejected；有效 3 事件→accepted=3；events_server 用 http.client 实测 POST（临时端口）。
commit: `feat: minimal /api/events endpoint (stdlib http, idempotent, validated)`

### Task 2: 事件→画像消费链（α 待定池）

**Files:** Create `talentforge/profile/pipeline.py`；Modify `talentforge/profile/engine.py`（暴露事件→主张推断）；Test `tests/test_pipeline.py`

**Interfaces:**
- `EVENT_TO_CLAIM_SYSTEM_PROMPT`（静态）——从单条/小批事件推断叙事/偏好主张 JSON：[{"text", "confidence", "kind": "narrative|preference"}]
- `ProfileUpdatePipeline(llm, engine: DefaultProfileEngine)`：
  - `async ingest_events(profile, events: list[dict]) -> Profile`：对事件批调 LLM 推断主张 → 转 NarrativeClaim(state=trial, sources=[{kind:"behavior", ref:event_id}]) → 与现有 trial claims 合并（文本相似去重，evidence_count 累积）→ 返回新 Profile
  - 简化信号累积：相同/相似主张文本重复出现 → evidence_count+1（不调 LLM，纯规则；与 update_from_feedback 的碎片匹配同思路）
- CLI：`talentforge events-ingest <jsonl>`（每行一个事件 JSON → 存库，不消费）+ `talentforge profile-update --profile <file> [--limit 50]`（从 events 表取最近 N 条 → pipeline 消费 → 存回 profile 文件）

**测试：** FakeLLM 返回主张 JSON → trial claims 生成 + evidence 累积；重复事件 → evidence_count 增长；events-ingest/profile-update CLI 离线 E2E（tmp events 文件 → 消费 → profile 文件出现 claims）。
commit: `feat: event-to-profile pipeline (trial claims with signal accumulation)`

### Task 3: 插件脚手架（TS MV3 工具链）

**Files:** Create `extension/`（package.json、tsconfig.json、vite 配置、manifest.json、src/ 骨架）；Test：npm 构建通过

**Interfaces（Produce）:** `npm run build` 产出 `extension/dist/`（content/kernel.js + bilibili.js + zhihu.js + background/service-worker.js）；manifest 注册：host_permissions=["http://127.0.0.1/*","*://*.bilibili.com/*","*://*.zhihu.com/*"]；content_scripts：bilibili(document_idle, isolated)、zhihu(document_idle, isolated)

**要点：** 工具链用 vite + 单入口构建（比 OpenBiliClaw 的复杂多入口简单）；TS strict；不引框架。package.json 脚本：build/typecheck/test（node --test 或 vitest——用 vitest 轻量）。
**测试：** `npm run typecheck` 过；`npm run build` 产出文件存在。
commit: `chore: extension scaffold (TS MV3 toolchain, manifest, build pipeline)`

### Task 4: 插件核心管道（kernel + buffer + flush）

**Files:** Create `extension/src/shared/types.ts`（BehaviorEvent/PlatformAdapter）、`extension/src/content/kernel.ts`（采集内核）、`extension/src/background/buffer.ts`（storage.local 持久缓冲）、`extension/src/background/service-worker.ts`（flush 30s + 消息路由）、`extension/src/shared/backend-endpoint.ts`；Test：vitest 单测

**Interfaces（照 OpenBiliClaw 契约，精简）:**
- kernel.startCollector(adapter)：监听 click/scroll/search/navigation（砍 hover/video dwell——最小闭环）→ 构造 BehaviorEvent → chrome.runtime.sendMessage({action:"BEHAVIOR_EVENT", data})
- buffer：enqueue（storage.local key talentforge_event_buffer，上限 50 条，满即 flush）、claim/flush/complete（简化：无 inflight/parking 复杂态，够用即可）
- service-worker：接收 BEHAVIOR_EVENT → buffer → 30s alarm flush → POST {base}/api/events
- backend-endpoint：默认 http://127.0.0.1:8420（无 auth——本机信任，M3 加密码门禁）

**测试：** vitest：kernel 在 mock DOM 上构造事件（bilibili 页面 → click 事件含 url/bvid）；buffer 持久化+满 50 flush；backend-endpoint URL 构造。
commit: `feat: extension core pipeline (kernel/buffer/flush/endpoint)`

### Task 5: B站 + 知乎 adapter

**Files:** Create `extension/src/shared/platforms/bilibili.ts`、`extension/src/content/bilibili.ts`、`extension/src/shared/platforms/zhihu.ts`、`extension/src/content/zhihu.ts`；Test：vitest adapter 解析

**Interfaces（adapter 契约）:** PlatformAdapter{sourcePlatform, detectPageType, extractContentId, cardSelector?, inferActionType, buildEventMetadata}；content 入口：startCollector(adapter)

**要点（照 OpenBiliClaw，只读精简）:**
- bilibili：pageType（video/space/search/其他）、contentId=URL 里的 bvid、动作识别（click 卡片/点赞按钮文案/搜索框输入）、metadata{title}
- zhihu：pageType（question/article/pin/search）、contentId=question/answer id、动作识别、metadata{title}
- 从侦察报告的 adapter 结构提炼（不照搬 DOM 细节——选择器按当前 B站/知乎 DOM 简写，够被动采集即可）
**测试：** 每个 adapter：fixture DOM → detectPageType/extractContentId/inferActionType 断言。
commit: `feat: bilibili + zhihu platform adapters`

### Task 6: 插件↔后端联调 + 收尾

**Files:** Modify `extension/manifest.json`（确认权限）；Create `docs/research/m2b-acceptance.md`；README 补 M2b 节

**要点：**
- 后端 events_server 与插件 flush 联调：手动起 server → 插件（或 curl 模拟）POST 事件 → 断言入库
- 验收笔记：后端单测/CLI 离线 E2E（可复现，记录实测）；真实浏览器采集标记 pending-user（授权后浏览 B站/知乎 → events 表有记录）
- README：M2b 使用节（后端起 server、插件安装/加载、events-ingest/profile-update 演示）
**测试：** 联调 E2E（curl 模拟插件 POST → events 表断言）；全测绿。
commit: `docs: M2b acceptance + README usage`

---

## 自审记录

- Spec 覆盖：spec-m2b §1↔Task1-6、§验收↔Task6、§不在范围 均未越界。
- 依赖顺序：T1（后端接收）→T2（消费链，依赖 T1 存储）→T3（插件脚手架，独立）→T4（管道，依赖 T3）→T5（adapter，依赖 T4）→T6（联调）。T3/T4/T5 是 TS 侧，与 T1/T2 Python 侧可并行——但 controller 串行派发更稳（避免 tests/ 与 extension/ 交错）。
- 已知风险：TS 工具链首次构建可能踩环境坑（node/npm 版本）；vitest 需要网络装包（阿里镜像对 npm 支持一般——用 npmmirror.com 镜像）。
- 无新 Python 依赖（stdlib http.server 替代 FastAPI，M3 再正式化）。
