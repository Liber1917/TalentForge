# M2b 规格 — 插件内容采集（B站 + 知乎）最小闭环

> 依据：spec-mvp-design.md §10 + D7/D22 + m2-extension-recon.md（插件架构侦察：核心循环 ~2100 行、每平台 ~220 行、OpenBiliClaw 三层模型 kernel+adapter+tap）。

## 交付范围

**目标**：验证"画像能自己长"链路——用户浏览 B站/知乎时插件只读采集行为 → 事件入库 → 消费进 profile 的 α 待定池（trial 主张 + 信号累积）。最小闭环，不铺 8 平台。

1. **Python 后端（先行，可独立测试）**：
   - `POST /api/events` 批量接收端点（BehaviorEvent 契约，含 event_id 幂等、not_initialized 语义——先做接收+存储，parking 简化）
   - `events` SQLite 表 + 事件归一化（source_platform/type/url/title/metadata）
   - **事件→画像消费链**：`ProfileUpdatePipeline` 轻量版——事件流进 α 机制：从事件推断的偏好/兴趣主张 → trial 态 `narrative_claims`（evidence_count 累积，复用 M1 的 update_from_feedback 信号累积模式）
   - CLI 命令 `talentforge events-ingest <jsonl>`（离线喂事件，便于无浏览器测试）+ `talentforge profile-update`（跑一次消费链）
2. **浏览器插件（TS MV3，照搬 OpenBiliClaw 机制）**：
   - 核心管道（kernel + buffer + service-worker flush + backend-endpoint + auth）——按侦察报告精简实现，只留只读采集必需部分
   - B站 adapter + 知乎 adapter（各 ~220 行：选择器/页面分类/内容 id 提取/动作识别）
   - manifest：host_permissions 仅本机后端 + bilibili.com + zhihu.com
   - 发送到本机后端 `POST http://127.0.0.1:8420/api/events`
3. **验收**：单元测试（后端契约 + 消费链 + 插件 TS 单测）；离线 E2E（`events-ingest` 喂假事件 → `profile-update` → profile 出现 trial 主张带证据）；真实浏览器采集标记 pending-user（用户授权后开 B站/知乎浏览验证采集入库）

## 不在本里程碑

- 8 平台横向铺开（管道跑通后按 adapter 模板复制）
- MAIN-world 写操作 tap（弹幕/评论/点赞捕获——只读采集先不做写操作）
- 验证码/风控对抗（浏览器内被动采集，无此问题）
- 事件→推荐/决策的完整回流（M3）
- 插件在线周期回拉/任务系统（OpenBiliClaw 的 task multiplex 全套——M2b 只做被动采集）

## 架构（三块）

```
浏览器插件 (TS MV3)                     Python 后端
├─ content/kernel.ts  采集内核          ├─ api/events.py    接收+存库
├─ content/bilibili.ts (adapter)       ├─ profile/pipeline.py 事件→α待定池
├─ content/zhihu.ts    (adapter)       └─ storage (events 表)
├─ background/buffer.ts 持久缓冲
├─ background/service-worker.ts flush
└─ shared/backend-endpoint.ts
        │ POST /api/events {events:[...]}
        ▼
```

## 测试策略

- 后端：events 端点单测（幂等/校验）、消费链单测（事件→trial 主张+证据累积）、CLI 离线 E2E
- 插件：TS 单测（kernel 事件构造、buffer 持久化、B站/知乎 adapter 解析——用 fixture DOM）
- 真实验收：pending-user（授权浏览器浏览→断言事件入库）
