# M3 Web 界面规格

> 依据：D21（交互全走 Web）、D11（反思性决策对话）、D9（三元+可解释链）、D13（提问式非灌输）、D17（证据原则）、D20（主张 α 机制+确认操作）、DESIGN.md（视觉系统）。本文定义三页面的布局/组件/状态/数据契约；视觉 token 全部引用 DESIGN.md，不重复定义。

## 0. 技术形态

- **服务**：FastAPI（升级现有 stdlib events_server → FastAPI 统一承载 API + 静态 Web；M3 起新依赖 fastapi+uvicorn）
- **前端**：无框架纯 HTML/CSS/vanilla JS（单页应用级别简单：三视图客户端路由 hash 切换）——不引 React/Vue（单人本地工具，构建链越薄越好；D8 自研轻量管线精神）
- **端口**：127.0.0.1:8420（与插件采集端点共存：/api/events 保留）

## 1. 对话首页（#chat）——陪伴入口

### 布局（单列居中 720px，DESIGN.md §4）

```
┌─ TopBar ──────────────────────────────────────┐
│ TalentForge ·  [画像一句话]  · 待定池 N  · ⚙    │
├─ ChatStream（滚动区）──────────────────────────┤
│ ChatBubble(user) / ChatBubble(assistant)       │
│   └ 内嵌卡片: DecisionCard / ClaimCard /       │
│              RiskNote / ReflectivePrompt       │
├─ Composer（底栏）──────────────────────────────┤
│ [输入框：想聊什么、想问什么、想投什么…]  [发送]   │
└───────────────────────────────────────────────┘
```

### 数据与交互契约

**GET /api/chat/turns**（初始化水合历史，限 50 条）→ `[{role, text, cards:[CardJSON], at}]`

**POST /api/chat/turns** `{text}` → SSE 流或轮询（M3 简化：同步返回 assistant 回复 + 0-N 张卡）：
- 后端路由：自由对话（画像上下文 LLM 回应）/ 触发决策（解析意图→跑 report 管线→返回 DecisionCard 批）/ 触发画像确认（返回 ClaimCard）
- 反思问题回答：卡内 ReflectivePrompt 的回复走同一端点（带 reply_to 卡 id）

**卡片 JSON 契约**（后端产出，前端渲染）：
```
DecisionCard: {type, job:{title,company,url,salary}, verdict, reason,
  risk_hits:[{key,label}], reflective_question, evidence:[{kind,ref,text}]}
ClaimCard:   {type, claim_id, text, state:trial, evidence_count,
  sources:[{kind,ref,at}], confidence}
RiskNote:    {type, key, label, why}
```

**操作端点**：
- `POST /api/claims/{id}/confirm` → state=active（D20 晋升须用户确认）
- `POST /api/claims/{id}/reject` → state=archived
- 响应更新流内对应卡（局部重渲染）+ TopBar 待定池数 -1

### 状态
- 流加载中：骨架行（border-subtle 底）
- LLM 回复中：Composer 禁用 + "正在思考…"（衬线斜体，参考书房语气）
- 卡片操作后：卡内状态 pill 原位变更（240ms 过渡，DESIGN.md §6）

## 2. 决策工作台（#jobs）——工具面

### 布局（>1024 双栏 2fr/3fr；小屏单列+Drawer）

```
┌─ TopBar（同上，tab 高亮"工作台"）────────────────┐
├─ 工具行: [搜索框] [城市选择] [verdict 筛选 pill] [生成报告] │
├──────────────┬────────────────────────────────┤
│ 岗位列表      │ 详情面板（选中项）                │
│ JobRow ×N    │ ├ 标题+公司+薪资+来源链接         │
│ ├ title      │ ├ VerdictBadge + 理由           │
│ ├ VerdictBadge ├ EvidenceChain（理由链展开）     │
│ └ company    │ ├ RiskNote ×N（可展开 why）      │
│              │ ├ ReflectivePrompt（回答进对话） │
│              │ └ gap/补短板列表                 │
└──────────────┴────────────────────────────────┘
```

### 数据与交互
- **GET /api/jobs?city=&verdict=&q=** → 列表（读 M2a SQLite jobs 表 + 最新 decisions 缓存表 M3 新增：job_url→verdict/reason/risk_json）
- **POST /api/report/run** `{query, city, limit, profile_path}` → 异步跑 M2a 报告管线（后台 task）→ `GET /api/report/status` 轮询 → 完成后列表刷新（复用 generate_report，产物落 decisions 表）
- 详情面板纯读 + 两个出口操作：「聊聊这个岗位」→ 跳对话页带上下文；ReflectivePrompt 回答 → POST /api/chat/turns
- JobRow 点击选中（active 态 border-strong），双击/按钮外链打开 JD 原文（target=_blank，canonical url）

### 状态
- 报告生成中：工具行进度条（"正在抓取/评估 12/20…"）+ 列表半透明
- 空态（无数据）：引导卡"还没有决策数据 → [去对话页聊聊] 或 [生成首份报告]"

## 3. 画像面板（#profile）——读/校对面

### 布局（三轨 + 待定池 + 八格；>1024 三栏，小屏纵向 tab）

```
┌─ TopBar（tab 高亮"画像"）───────────────────────┐
├─ 画像头部: [姓名] 一句话叙事(identity) [导出JSON] │
├─ Tab: 待定池(N) | 叙事轨 | 效用轨 | 结构位置     │
├────────────────────────────────────────────────┤
│ 待定池: ClaimCard 列表（trial 态，操作同对话页）   │
│   + active/archived 折叠区（历史主张）            │
│ 叙事轨: identity/values/deep_drives 只读卡        │
│   + NarrativeClaim 全列表（按状态分组）           │
│ 效用轨: OrdinalPreference 列表（属性→偏好序）      │
│   + overrides 标记（用户手改过的，D18）           │
│ 结构位置: 八格卡片网格（D17）                     │
│   + market_assessment 灰置提示"岗位数据积累后启用" │
└────────────────────────────────────────────────┘
```

### 数据与交互
- **GET /api/profile** → Profile 全量 JSON（M1 schema 直出）
- **POST /api/profile/claims/{id}/confirm|reject**（同对话页端点，操作后两视图同步——简单实现：操作后刷新两页数据）
- 校对流（D21 简版）：`POST /api/profile/resume-review` `{resume_file}` → 返回抽取文本 diff 视图（原文 vs 解析字段）→ 用户逐项 [确认][修改] → 确认项入 Profile 显式层
- 导出：`GET /api/profile/export` → 下载 JSON

### 状态
- 待定池空态："还没有待验证的主张——浏览 B站/知乎 或聊聊你自己，我会开始留意"
- 证据链 loading：锚点行骨架

## 4. 跨页组件契约

| 组件 | 数据源 | 交互 |
|---|---|---|
| VerdictBadge | verdict 字段 | 纯展示（色+字，DESIGN.md §2 三值语义） |
| EvidenceChain | evidence[] / sources[] | 展开/收起；锚点 mono 显示 ref+at |
| ClaimCard | ClaimJSON | 确认/驳回/聊聊（聊聊→带 claim 上下文跳对话页） |
| RiskNote | risk_hits | 展开 why；不提供"忽略"（风险是知情信息，不消失） |
| ReflectivePrompt | reflective_question | 内嵌输入框回答 → POST chat/turns（reply_to） |

## 5. 后端新端点汇总（M3 API 面）

| 端点 | 方法 | 用途 | 复用 |
|---|---|---|---|
| /api/chat/turns | GET/POST | 对话流 + 卡片产出 | LLM client + 意图路由（新） |
| /api/claims/{id}/confirm·reject | POST | α 晋升/驳回 | profile engine（新薄层） |
| /api/jobs | GET | 工作台列表 | storage list_jobs + decisions 缓存 |
| /api/report/run · /status | POST/GET | 异步报告 | M2a generate_report |
| /api/profile | GET | 画像直出 | Profile schema |
| /api/profile/resume-review | POST | 抽取校对 | resume_io（新薄层） |
| /api/profile/export | GET | 导出 | 序列化 |
| /api/events | POST | 插件采集（保留） | M2b 已有 |
| / （静态） | GET | 三视图 SPA | FastAPI StaticFiles |

## 6. M3 范围外

- WebSocket 推送（轮询够用）；暗色模式实现（token 已备）；移动端深度优化（响应式保底即可）
- 浏览器插件任务系统、自动投递（D2 维持）
- 多简历/多画像实例

## 7. 验收口径

- 三页面可离线演示：假数据 JSON 驱动全部卡片渲染（无 LLM 也能看界面）
- 对话页端到端：真问一句"帮我看看深圳后端岗"→ 决策卡流入
- 主张确认：对话页/画像页任一处确认 → 两页状态同步
- 视觉：DESIGN.md token 全落地（无裸 hex），Primitive Showcase 通过（Card/VerdictBadge/ClaimCard/EvidenceChain 四原语先过 375/768/1280 三断点）
