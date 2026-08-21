# M2 浏览器插件内容采集 — OpenBiliClaw 机制侦察报告

日期：2026-08-21
来源：/home/OpenBiliClaw/extension（MV3 + TypeScript，v0.3.207）
目标：TalentForge M2（8 平台只读采集）借鉴机制而非照搬
方法：只读侦察，结论均带 file:line 证据

---

## 0. 总览：借鉴结论（TL;DR）

OpenBiliClaw 的采集架构是 **"通用内核 kernel + 每平台 adapter + MAIN-world 可选 tap"** 三层模型：

- **核心循环（平台无关，一次写好全平台复用）**：content script 埋点 → `chrome.runtime.sendMessage({action:"BEHAVIOR_EVENT"})` → service worker 持久化缓冲（chrome.storage.local 镜像）→ 批量 `POST /api/events`。最小可借鉴集约 **2100 行**（含 dwell 跟踪；砍掉可到 ~1900 行）。
- **单平台适配（每平台增量）**：以 bilibili 为例，**2 个文件约 220 行**（content 入口 130 行 + adapter 89 行）+ manifest 注册 ~15 行。若还要捕获"写操作"（弹幕/评论/点赞），需另加 MAIN-world tap（bili 340 行，dy 高达 1636 行）。
- **8 平台 vs 2-3 平台差异**：核心循环与通信层 **零改动**；差异只在平台适配层（~220-600 行/平台）与可选的 MAIN tap。工程切分建议：**先 2-3 平台打通管道，再横向复制 adapter**。

---

## 1. manifest.json：注册模式

文件：/home/OpenBiliClaw/extension/manifest.json

- **permissions**（:6-14）：`activeTab, alarms, cookies, notifications, scripting, sidePanel, storage` — 采集本身只强依赖 `storage`（缓冲持久化）+ `alarms`（定时 flush）；`cookies`/`scripting`/`sidePanel` 服务于任务派发与 UI，M2 可砍。
- **host_permissions**（:15-33）：按平台通配符逐一列出（`*://*.bilibili.com/*` 等 13 个站点）+ 本机后端 `http://127.0.0.1/*`、`http://localhost/*`（:31-32）。M2 只需要本机后端 + 目标平台。
- **content_scripts 注册模式**（:41-199，16 个条目）：**每平台两条**：
  1. **isolated world 主采集**：`run_at: "document_idle"`，如 bilibili（:41-50）→ `dist/content/bilibili.js`
  2. **MAIN world 网络 tap**（可选，用于捕获写操作）：`run_at: "document_start", "world": "MAIN"`，如 bilibili（:51-60）→ `dist/main/bili-interact-tap.js`
  - 纯只读采集只需第 1 条；douyin 的 MAIN tap 还进了 `web_accessible_resources`（:200-209）。
- **background**（:38-40）：单一 service worker `dist/background/service-worker.js`。

## 2. 核心采集循环（问题 1：最小可借鉴集）

链路：**content 埋点 → runtime message → SW 缓冲（storage.local 镜像）→ 批量 POST**。各环节证据：

### 2.1 埋点层：通用内核 kernel.ts（492 行，平台无关）

文件：/home/OpenBiliClaw/extension/src/content/kernel.ts

- `startCollector(adapter: PlatformAdapter)`（:50）一次性注册全部 DOM 观察器，全部事件经 `sendEvent` → `chrome.runtime.sendMessage({action:"BEHAVIOR_EVENT", data: event})`（:40-42）：
  - **click**（:278-336）：捕获点击 + 经 `inferActionType` 识别强信号（like/coin/favorite/comment/share/follow/dislike/retraction）
  - **scroll**（:183-237）：600ms debounce（:22, :219-225），记录 scrollRatio
  - **hover**（:239-276）：800ms 悬停判定 + 200ms throttle（:21, :23）
  - **search**（:171-181）：搜索框 Enter + URL 派生查询（:164-169），带 1s 内同 query 去重（:150-159）
  - **navigation**（:454-473）：patch `pushState`/`replaceState`（:427-452）+ `popstate` + `pagehide`，SPA 路由变化即发 `snapshot`
  - **video**（:340-397）：play/pause/seek/view 事件 + 分段 dwell 跟踪（`VideoDwellTracker`，:64-83）
  - **snapshot**（:32, :142-144）：navigation/view/强信号事件携带 DOM 快照
- 平台差异全部收敛到 `PlatformAdapter` 接口（见 §4），kernel 不感知具体站点。

### 2.2 缓冲层：buffer.ts（552 行）

文件：/home/OpenBiliClaw/extension/src/background/buffer.ts

- **MV3 关键设计**：SW 约 30s 空闲即回收，内存缓冲会丢，因此**每次变更都写穿 chrome.storage.local 镜像**（:16-24 注释），恢复在 `bufferReady()` 异步门后（:221-226）。
- 存储 key（:27-31）：`obc_event_buffer`（live 镜像）、`obc_event_inflight`（发送中批次，ack 后清）、`obc_parked_events`（后端未初始化时停车）。
- 容量：live 上限 50（:33）、parked 上限 500（:35）、parked TTL 48h（:37）。
- 核心函数：
  - `enqueueEvent`（:289-318）：入队 + 写穿镜像，失败抛错让发送方收到负 ACK
  - `enqueueEventWithDurableAck`（:333-361）：返回 `true` 保持消息端口存活直至镜像落盘
  - `claimBufferedEventsForFlush`（:254-268）：claim 一批 → 转 inflight（每个崩溃窗口都有归属者）
  - `completeInflightEvents`（:271-282）：**仅在后端 ack 后**清除 inflight
  - `parkEvents`/`drainParkedEvents`（:391-480）：后端 not_initialized 时停车、初始化后回灌
  - 去重：`event_id` 幂等（:146-150）+ 高频事件桶去重（scroll/hover/snapshot，:505-514）
  - 立即 flush 判定：强信号类型 + 视频点击（:542-552, :3-13）

### 2.3 发送层：service-worker.ts flush（927 行中的 ~120 行相关）

文件：/home/OpenBiliClaw/extension/src/background/service-worker.ts

- 节奏：`BUFFER_FLUSH_INTERVAL = 30_000`（:133）+ `FLUSH_ALARM_NAME`（:134）；alarm 每 30s 触发（:839-868），缓冲满或强信号时入队后立即 flush（:832-836）。
- `flushEvents()`（:523-580）核心流程：
  1. `claimBufferedEventsForFlush()`（:530）
  2. `authenticatedFetch(apiUrl("/events"), {method:"POST", body: JSON.stringify({events})})`（:534-538）
  3. 非 2xx → **保留 inflight 不动**，下轮重试（:540-545）
  4. 响应 `not_initialized` → `parkEvents`（:557-565）；否则 `completeInflightEvents` + `drainParkedEvents`（:566-571）
- 消息监听（:826-837）：`action === "BEHAVIOR_EVENT"` → `enqueueEventWithDurableAck(event, sendResponse, ...)`，持久化成功才回 ACK。

### 2.4 最小可借鉴集清单（一次写好，全平台复用）

| 文件 | 行数 | 用途 |
|---|---|---|
| src/shared/types.ts | 126 | BehaviorEvent + PlatformAdapter 接口 |
| src/shared/behavior.ts | 147 | createBehaviorEvent / DOM 快照 / action hint |
| src/content/kernel.ts | 492 | 通用采集内核（click/scroll/hover/search/nav/video） |
| src/content/video-dwell-tracker.ts | 195 | 停留时长跟踪（可砍） |
| src/background/buffer.ts | 552 | MV3 持久化缓冲 |
| src/background/service-worker.ts | 927（采集相关 ~120） | flush + 消息监听 + alarm |
| src/shared/backend-endpoint.ts | 337 | endpoint 解析（可精简到 ~60） |
| src/shared/auth.ts + token-store.ts | 115 + 154 | device-key 换 Bearer（M2 可简化） |

**合计约 2100 行**（含 dwell 与完整 endpoint/auth；砍 dwell、简化 auth/endpoint 可压到 ~1500-1600 行）。这些一次写好，**8 平台全部复用，零增量**。

## 3. bilibili 平台适配（问题 2：最小工作面）

### 3.1 文件构成（只读采集）

| 文件 | 行数 | 职责 |
|---|---|---|
| manifest.json content_scripts 条目 | ~15 行（:41-60 第一条即可） | isolated world, document_idle |
| src/content/bilibili.ts | 130 | 入口：`startCollector(bilibiliAdapter)` + 事件桥接 |
| src/shared/platforms/bilibili.ts | 89 | adapter：选择器/页面分类/bvid/动作识别 |

**只读采集增量 ≈ 220 行 + manifest 15 行。核心循环零改动。**

### 3.2 证据细节

- 入口（content/bilibili.ts）：
  - `startCollector(bilibiliAdapter)`（:110-112）— kernel 接管全部 DOM 采集
  - `window "message"` 监听 `source: "obc-bili-interact"`（MAIN tap 的 postMessage，:117-123），经 `buildEventFromBiliInteraction`（:53-95）归一化为统一 `BehaviorEvent` 后走同一 `sendEvent`（:97-103）→ `BEHAVIOR_EVENT`
  - 文本消毒在客户端做第一道（:62, :23）
- adapter（shared/platforms/bilibili.ts）：
  - `CARD_SELECTOR`（:12-18）、`SEARCH_INPUT_SELECTOR`（:20-21）
  - `detectBilibiliPageType`（:23-29）：video/search/user/category/home 五类
  - `extractBvid`（:31-33）：`/BV[0-9A-Za-z]{10}/` 正则
  - `inferBilibiliActionType`（:39-62）：中文关键词 → like/coin/favorite/comment/share/follow/dislike
  - `tapAuthoritativeActions`（:71-77）：comment/like/favorite/coin/retraction 交给 MAIN tap，DOM 路径抑制防双计
- 可选 MAIN tap（写操作捕获，M2 只读可砍）：src/main/bili-interact-tap.ts（**340 行**）。

### 3.3 平台难度差异（重要）

各平台被动采集复杂度差异极大（含任务系统行数）：

- bilibili：content 130 + adapter 89（简单）
- xhs：bootstrap 1051 + passive 271 + selectors 41 + risk-control 161 + ...（**复杂**，有风控对抗）
- douyin：MAIN tap dy-fetch-tap.ts **1636 行**（复杂）
- x：x-graphql-tap.ts 457 行（中等）

→ 8 平台工程量不是 8 倍线性，而是「2-3 个简单平台 ≈ 1 个复杂平台」。

## 4. 插件↔后端通信契约（问题 3）

### 4.1 Endpoint

文件：/home/OpenBiliClaw/extension/src/shared/backend-endpoint.ts

- 默认：`http://127.0.0.1:8420`（:22-24）
- 存储 key：`popup_backend_endpoint`，值 `{scheme, host, port}`（:25, :121-136）；三端（popup/SW/content）共同读写，`chrome.storage.onChanged` 订阅实时生效（:138-162）
- 构造：`apiUrl(path)` → `http://host:port/api/path`（:186-190）；`wsUrl(path, token)` → `ws://host:port/api/path?token=`（:192-199）

### 4.2 认证

文件：/home/OpenBiliClaw/extension/src/shared/auth.ts + token-store.ts

- 首次：`POST /api/auth/extension-token`，body `{key: deviceKey}` → `{ok, token, expires_at}`（auth.ts:32-61）
- 之后所有请求带 `Authorization: Bearer <token>`（auth.ts:86-91）；401 时强制刷新 token 重试一次（auth.ts:100-104）
- 存储 key：`obc_extension_device_key`（token-store.ts:3）、`obc_auth_session`（token-store.ts:4）

### 4.3 事件 Schema

文件：/home/OpenBiliClaw/extension/src/shared/types.ts

```
BehaviorEvent（:10-20）{
  event_id?: string      // 生产者生成，跨 storage/重试/parking 保幂等
  type: string           // click|scroll|hover|search|view|pause|seek|snapshot
                         // + 强信号 comment|like|favorite|coin|share|follow|feedback（buffer.ts:3-13）
  url: string
  title: string
  timestamp: number
  source_platform: string  // "bilibili" 等
  context: { pageType; domSnapshot?; viewport{width,height}; scrollPosition }
  metadata: Record<string, unknown>  // 平台附加：bvid / content_id / comment_text 等
}
```

### 4.4 传输协议

| 方向 | 契约 | 证据 |
|---|---|---|
| content → SW | `chrome.runtime.sendMessage({action:"BEHAVIOR_EVENT", data: BehaviorEvent})`，返回 `{ok:true}`（已持久化）或 `{ok:false, error:"persist_failed"}` | kernel.ts:40-42；buffer.ts:333-361；service-worker.ts:826-837 |
| SW → 后端 | `POST /api/events`，body `{events: BehaviorEvent[]}` | service-worker.ts:534-538 |
| 后端响应 | 200 + JSON：`{ok:true}`；或 `{ok:false, error:"not_initialized"}`（触发 parked） | service-worker.ts:540-556 |
| flush 触发 | 30s alarm + 强信号/满 50 条立即 flush | service-worker.ts:133-134, 832-836；buffer.ts:33, 542-552 |
| 健康检查 | `GET /api/ping`（2s 超时）、`GET /api/health`（12s） | service-worker.ts:381-396, 142-146 |

### 4.5 事件类型与去重（buffer.ts）

- 高频类型（scroll/hover/snapshot）按 `type:url:时间桶` 去重（:505-514）
- 强信号类型（comment/coin/favorite/feedback/follow/like/share/view）立即 flush（:3-13, :542-552）

## 5. 新增平台最小文件清单与工程量对比（问题 2/结论）

### 5.1 新增一个平台（只读采集）的文件清单

```
1. manifest.json         +1 条 content_scripts（isolated world, document_idle, ~15 行）+ host_permissions 条目（~1 行）
2. src/content/{p}.ts    ~130 行（模板：startCollector(adapter) + 平台事件桥接）
3. src/shared/platforms/{p}.ts  ~90 行（adapter：选择器/页面分类/ID 提取/动作关键词）
── 合计 ~235 行/平台，核心循环与通信层零改动 ──
（可选）src/main/{p}-tap.ts  +100~1600 行（写操作捕获，M2 只读可砍）
（可选）task 派发子系统        +60~1700 行/平台（M2 不需要，OpenBiliClaw 专有）
```

### 5.2 8 平台 vs 先 2-3 平台

| 项 | 固定成本（一次） | 每平台增量 |
|---|---|---|
| 核心循环（kernel/buffer/flush/通信） | ~2100 行 | 0 |
| 平台适配（只读） | 0 | ~235 行 |
| MAIN tap（可选） | 0 | 100~1636 行（平台差异大） |
| 任务派发（M2 不做） | 0 | 60~1700 行 |

- **8 平台总增量（只读）**：~235 × 8 ≈ **1900 行**，且机械重复、风险低。
- **主要风险在核心管道**（MV3 SW 回收、缓冲持久化、去重、ack 语义），与平台数无关。
- **建议**：先 2-3 平台（如 bilibili + zhihu/reddit 这种简单平台）验证管道与后端契约，再横向铺开；复杂平台（xhs/douyin）单独排期（风控对抗 + MAIN tap 大文件）。

## 6. 对 TalentForge 的借鉴要点

1. **照搬三层模型**：kernel（通用）+ adapter（平台）+ 可选 tap；不要每个平台写独立采集器。
2. **照搬持久化缓冲**：storage.local 写穿镜像 + inflight 所有权 + event_id 幂等 —— 这是 OpenBiliClaw 踩过 MV3 SW 回收坑后的成熟解（buffer.ts:16-24）。
3. **简化点**：M2 只读，可砍 auth 的 device-key 换 token 流程（直接本机 localhost 信任）、可砍 WS 推送、可砍任务派发/backfill 子系统。
4. **契约先定**：`POST /api/events {events}` + `not_initialized` parking 语义是后端联调的关键接口，TalentForge 后端需先实现（或先 mock）。
5. **注意**：MAIN world tap 依赖站点 DOM/网络结构（如 bili-interact-tap 拦截弹幕发送），站点头部改版即碎，是长期维护成本最高的部分 —— M2 只读策略恰好避开。

---
（报告完）
