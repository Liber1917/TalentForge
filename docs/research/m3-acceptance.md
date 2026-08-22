# M3 验收笔记 — 三视图 Web 界面（对话/工作台/画像）

> 验收依据：`docs/spec-m3-web.md` §7（验收口径）；`docs/plan-m3.md` Task 8。
> 验收日期：2026-08-22。执行人：agentic worker（Task 8）。
> 结论速览：**离线假数据演示通过（可复现，记录见 §1）；真后端联调通过（fake/真实 LLM 环境，三视图数据流见 §2）；全测绿：pytest 137 + web node:test 51（§3）；真实 Boss 抓取与插件↔后端端到端标记 pending-user（§4），不阻塞本里程碑收尾。**

---

## 1. 离线假数据演示验收（已通过，可复现）

**起服：**

```bash
python -m uvicorn talentforge.api.app:create_app --factory --port 8420
```

**浏览器打开 http://127.0.0.1:8420/** ——默认数据源即离线 fixtures（前端 `api.js` 缺省 `USE_FIXTURES=true`，三视图用本地镜像 fixture 渲染，无需 LLM / 无需数据库）。hash 路由导航：`#/chat` 对话首页 / `#/jobs` 决策工作台 / `#/profile` 画像面板。

**三视图渲染内容实测：**

### 1.1 对话首页 `#/chat`

- 5 轮 fixture 对话（用户→助手→用户→助手→用户），首屏即见完整聊天流与内嵌卡片。
- 4 类卡片契约齐全：
  - **DecisionCard ×2**：`Python 后端工程师（星辰科技，25-50K·16薪，verdict=hold，996 风险命中 + EvidenceChain 双证据 jd/dialogue）`、`高级后端开发 Java（云帆信息，15-25K，verdict=skip，竞业限制风险命中 + deal-breaker 证据）`。
  - **ClaimCard ×1**：`claim-demo-sysdes-01`（"分布式/系统设计深度积累"），state=trial、confidence=0.75、sources[0]={kind:dialogue, ref:turn-3}，带确认/驳回操作。
  - **RiskNote ×1**：`996 工作制`，why 展开为知情权衡说明。
  - **ReflectivePrompt ×1**：内嵌输入框"怎么权衡 996"，回答走同一 composer。
- Composer 输入 → 本地 mock 回复；ReflectivePrompt 回答 → mock 追加对话 + 局部更新（fixtures 模式）。

### 1.2 决策工作台 `#/jobs`

- **8 个深圳后端岗位三态列表**：apply ×2（观澜数据 / 睿达网络）、hold ×2（星辰科技 / 海天互娱）、skip ×4（云帆信息 / 星环科技 / 方舟金融 / 微光教育），VerdictBadge 前置。
- **筛选**：搜索（title/company/location/salary 模糊）、城市选择、verdict pill 过滤。
- **详情面板**（点选 JobRow）：标题+公司+薪资+来源链接、VerdictBadge+理由、**EvidenceChain**（理由链展开/收起）、**RiskNote** 展开 why、**ReflectivePrompt**（回答进对话）、**gap/补短板**列表（如观澜数据 gap=Flink 流处理 + remediation 两条）。
- **生成报告**：fixtures 模式本地 mock（按钮变"报告中…"禁用 → 恢复 + 状态提示）。

### 1.3 画像面板 `#/profile`

- **四个 tab**：
  - **待定池（N=3）**：trial ClaimCard ×3（claim-demo-01~03）+ active ×1（claim-demo-active-01，模拟用户已确认，evidence_count+1），带确认/驳回/聊聊操作；active/archived 折叠区。
  - **叙事轨**：identity（"深耕后端基础设施的工程师"）/ values / deep_drives 只读卡 + NarrativeClaim 列表。
  - **效用轨**：OrdinalPreference ×5（salary / work_mode / location / company_type / tech_stack 各属性→偏好序）。
  - **结构位置**：八格卡片网格（cash_buffer / stage / city_constraints / family_duty / support_network / economic_independence / reservation_wage / exploitation_redlines / reproduction_costs / mobility 等格）。
- **简历校对 mock**：fixtures 模式本地示例区块（file=resume_demo_2026.pdf，抽取 vs 原文 diff 视图，逐项确认）。
- **导出 JSON**：fixtures 模式本地 Blob 下载（缩进 2 的完整 profile）。

### 1.4 Primitive Showcase

- `/showcase.html`：五原语（Card / Btn / VerdictBadge / ClaimCard / EvidenceChain）全落地，**375 / 768 / 1280 三断点**逐原语核对通过（拖动窗口过断点，布局与触控目标正常）。

**验收判定：** ✅ 通过——三视图离线可演示，假数据驱动全部卡片渲染，无 LLM 也能完整看界面（spec §7 第一条）。

---

## 2. 真后端联调验收（fake/真实 LLM 环境，三视图数据流）

**切换**：URL 加 `?real=1`（或 localStorage 置 `tf_real=1`）→ 前端 `api.js` 的 `BASE` 从 `/api/fixtures` 切到 `/api`，命中 FastAPI 真端点。

**端点数据流实测（fake LLM 环境 = 测试套件注入 FakeLLM；真实 LLM 环境 = 本机 LLM 凭据）：**

| 端点 | 方法 | 联调行为 |
|---|---|---|
| `/api/chat/turns` | GET | 空对话历史时给欢迎语（"我是 TalentForge——你的求职决策伙伴…"）；进程内存态，重启即空 |
| `/api/chat/turns` | POST | 意图路由三分支（关键词版，见 routes_chat.py `_intent`）：**决策触发**（text 含 投/看看/岗位/工作/推荐/报告）→ 跑 `generate_report` 出 DecisionCard 批 + RiskNote + ReflectivePrompt；**自由对话** → LLM 回复 + 提及自身时经 ProfileUpdatePipeline 沉淀 trial claim 卡；**reply_to 反思回答** → 回答沉淀为 trial claim（dialogue 来源 ref=问题） |
| `/api/jobs` | GET | 读 M2a jobs 表 + decisions 缓存；verdict 取缓存或 `estimate_verdict` 缺省估算（deal-breaker→skip / 有风险→hold / 否则 apply）；city/verdict/q 过滤；空库返回 `[]` |
| `/api/profile` | GET | 三轨契约直出（narrative / utility_preferences / structural_position）+ narrative_claims |
| `/api/claims/{id}/confirm` `/reject` | POST | 状态变更写回画像文件（trial→active / →archived），返回 ClaimCard |
| `/api/report/run` → `/api/report/status` | POST/GET | 起后台任务跑 M2a 报告管线 → 轮询 status（running/done/failed），产物落 decisions 缓存 |
| `/api/profile/resume-review` | POST | resume_io 抽取文本 → diff 视图（原文 vs 解析字段 identity/skills/years/full_text） |
| `/api/profile/export` | GET | 下载完整 profile JSON（Content-Disposition） |

**验收判定：** ✅ 通过——三视图真实数据流全部打通，卡片产出、状态变更、异步报告、画像读写均复用 M1/M2a/M2b 组件（ProfileUpdatePipeline / generate_report / CoarseMatcher / storage / resume_io）。

---

## 3. 验证证据

| 项 | 结果 |
|---|---|
| Python pytest | **137 passed** |
| web node:test（web/tests/chat·jobs·profile.test.mjs） | **51 passed**（14+17+20） |
| 冒烟联调（uvicorn 起服实测） | 见下 |

**冒烟联调记录（真实 LLM 环境，uvicorn 起服 http://127.0.0.1:8420）：**

1. `GET /api/health` → **200** `{"ok": true}`
2. `GET /api/profile` → 契约完整：**6 claims 三轨**（narrative/utility/structural 齐备）
3. `GET /api/jobs`（空库）→ **`[]`**（前端空态引导：去对话页聊聊 / 生成首份报告）
4. 自由对话 `POST /api/chat/turns`（"我想去深圳做后端，主攻分布式"）→ 真实 LLM 回复 + **2 张隐式主张卡**（ProfileUpdatePipeline 沉淀 trial claim 写回画像）
5. 决策触发（"帮我看看岗位"）空库 → 引导文案（"现在还没有可评估的岗位数据…"），不 500
6. seed 2 岗后再决策触发 → **决策卡 / 风险卡 / 反思卡齐全**（DecisionCard 批 + RiskNote + ReflectivePrompt）
7. `decisions` 缓存联动：报告产出写缓存后 `GET /api/jobs` verdict 刷新（缓存优先）
8. 静态资源全 **200**（/、/showcase.html、css/js/partials 均正常）

---

## 4. 限制说明与验收结论

### 限制（明确范围，不视为缺陷）

| 限制 | 说明 |
|---|---|
| 对话历史为进程内存态 | `app.state.chat_turns`，重启即空（spec §1 注明后续接持久化） |
| gap / remediation 无数据源 | 工作台详情"补短板"仅 fixture 模式有值；真模式缺口留空（无对应数据源） |
| verdict 缺省估算 | 无 decisions 缓存时 `estimate_verdict` 为中性近似（deal-breaker→skip / 有风险→hold / 否则 apply），非 LLM 细判 |
| 真实 Boss 抓取 | pending-user——需用户授权 cookie（同 M2a §2）后方可跑"生成报告"真抓取 |
| 插件↔后端端到端 | pending-user——需用户授权浏览器加载扩展（同 M2b §2） |
| 真实 LLM 意图路由 | 为关键词版（DECISION_KEYWORDS / CHAT_KEYWORDS），后续可换 LLM 意图分类（plan 已注明） |
| resume 解析 | 规则启发式词表（非 LLM 结构化抽取，deviation 已注） |

### 验收结论

**✅ 通过项清单：**

- [x] 三视图可离线演示（对话 5 轮 + 4 类卡片 / 工作台 8 岗三态 + 筛选 + 详情 / 画像四 tab + 八格），无 LLM 可看界面
- [x] Primitive Showcase 五原语 375/768/1280 三断点
- [x] 真后端三视图数据流（chat 意图路由 / jobs 缓存联动 / profile 契约 / claims 状态写回 / report 异步轮询 / resume-review / export）
- [x] 冒烟联调 8 项全过（health 200、空库 `[]`、真实 LLM 回复 + 隐式主张卡、空库引导、seed 后卡片齐全、decisions 联动、静态资源全 200）
- [x] 全测绿：pytest 137 + web node:test 51

**pending-user（不阻塞收尾）：** 真实 Boss 抓取（M2a cookie）、插件↔后端浏览器端到端（M2b 扩展授权）。
