# TalentForge — SDD 设计决策与开放问题

> 状态：计划阶段（SDD brainstorming）。本文件随设计讨论持续更新，是规格文档（spec）的源头。

## 已确认决策

| # | 主题 | 决策 |
|---|------|------|
| D1 | 核心定位 | 全生命周期平台 × 陪伴式决策助手 |
| D2 | 自动投递 | MVP 后再定（不在 MVP 范围，不移植 jobclaw applier/） |
| D3 | 目标用户 | 信息类同学（计算机/自动化，校招/应届） |
| D4 | MVP 形态 | 端到端最小垂直切片（画像→抓取→匹配→决策→可解释报告） |
| D5 | 闭环形态 | 显式输入 → 画像/胜任力 → 决策报告 →（反馈回流）→ 画像增量修正 |
| D6 | 画像输入原则 | 显式优先：简历/配置为主输入，行为流仅做增量修正 + 洞察 |
| D7 | 交互面 | CLI + 本地 Web + 浏览器插件（插件只读采集，MVP 用薄 content script） |
| D8 | 技术栈 | Python 3.11+ / SQLite / 单人本地 |
| D9 | 决策输出形态 | 三元决策（投/观望/不投）+ 可解释链（画像证据 × 胜任力维度 × JD 原文）+ 差距 + 补短板 |
| D10 | 产品北极星 | 锻造人才，非迎合市场。人的模型 = 人格叙事轨 + 偏好/效用轨 双轨，缺一不可 |
| D11 | 人在闭环交互形式 | 反思性决策对话：决策卡（三元+可解释链+结构性追问）→ 苏格拉底对话完成反思与选择 → 反馈回流 |
| D12 | 结构维度 | 双轨须结构化理解（叙事=结构中成为谁；偏好=欲望被结构如何塑造）；独立建模「场域」（劳动力市场政治经济学）；决策链三维：市场契合 × 成长契合 × 结构认知 |
| D13 | 最高交付与方法 | 增强认识世界改造世界的能力（世界观/认识论/方法论）；方法=提问式（弗莱雷），非灌输；批判意识的助产士，非教师 |
| D14 | 批判层 MVP 深度 | 从第一个垂直切片就内置（决策卡自带结构性追问 + 结构性风险提醒），非后加 |
| D15 | 稳定核心+可拓展外围 | 锁定：decision（三元+可解释链+追问）、feedback 闭环。可拓展（Protocol+默认实现）：profile / competency / field / sources / matcher——研究阶段未定论，须可替换。依赖倒置：核心只依赖 schema 类型，不依赖具体实现 |
| D16 | O1 画像机制决议（部分） | ①Option C 为底（M0 三轨即结构）；②假设机制=方案α：narrative_claims 可选附加字段、trial/archived 两态、隐式证据累积、active+晋升流推迟 M3 且须用户确认、provisional 可整体移除；③读人方法=精神分析式：从用户消化/生产的内容分析欲望结构（与 TalentModel-skill 拉康入口同源），素材多少不预设、具体问题具体分析；④素材=路线b内容采集，国内平台8个：B站/知乎/小红书/抖音/微博/V2EX/Bangumi/Linux.do（砍YouTube/X/Reddit），沿用 OpenBiliClaw 插件只读采集机制。详见 docs/deliberations/O1-profile-depth.md §7（小确认2/3待决） |
| D17 | 结构位置=八格设计（R3） | StructuralPosition 八格：①现金流缓冲②身份/约束③支持网络④依赖承担⑤定价底牌⑥剥削敏感带⑦再生产账单⑧流动性与时点。理论=政治经济学+西马计量。**证据原则**：信息不对称是剥削的一环——格子5/8市场侧由系统从岗位数据估（带证据标注），用户只填自己那半；硬信息系统不猜；猜测只进待定池且带证据链。详见 O1 §7 R3 |
| D18 | 词表护栏+用户确认权 | 词表版本化、规则匹配兜底、OOV落桶、存规范id；**词表替换必须经用户确认**——规范词是用户查询/澄清自己档案的检索锚点，静默替换切断用户与档案的对应。与"晋升须确认"同一条红线：任何改变用户可见档案语义的操作都过用户之手 |
| D19 | O1 收口 | O1 状态=accepted（R0-R3+三个小确认全部裁决）。选项C为底+α假设机制+精神分析式读人+内容采集8平台+八格结构位置+词表护栏。M1 地基齐备 |
| D20 | O2 简历包装决议（accepted） | ①包装=中性（不判死刑/不扣分，风格入叙事轨中性记录）；②所有主张统一走α机制：trial/unverified→多源证据累积（行为/反馈/对话/上传证明）→verified；③转正后有时效（借鉴OpenBiliClaw时效三态：有效/待复审/过期）——能力随时间变化；④匹配只吃"证据够"的主张（verified_skills 分离，未验证只作参考）；⑤潜力=变化率（追踪轨迹非快照）；⑥契约红线：不碰 feedback/FeedbackEvent，verified 不进 Literal，全 additive；⑦时间窗硬边界（一校招周期未验证即 archived）。详见 docs/deliberations/O2-resume-packaging.md |
| D21 | 校对等交互全走 Web | 简历抽取校对、主张验证确认、画像编辑等一切用户交互面统一走 Web（M3 前端范围）；CLI 保持纯命令工具定位，不做交互式确认 |
| D22 | M2 方案定稿 | ①M2a（Boss岗位链路：Playwright抓取→Job归一化→场域最小版→匹配粗版→三元决策报告）先行，M2b（插件内容采集）后铺；②首批平台B站+知乎，OpenBiliClaw式被动采集（用户浏览自动记录，照搬核心管道~2100行机制）；③匹配先粗后细——M2a用FitLevel高低两档（够决策象限），序数偏好精排后置 |
| D23 | M4 作品源（backlog，M3 后启） | ①新源类型"作品源"（主动拉取适配器，区别于浏览采集）：GitHub/Gitee API（公开 repo：语言分布/star/commit 活跃度/README）+ arXiv API（按作者查论文：标题/摘要/venue/作者排序/时间）；知网无公开 API 不做。②信号性质=稀疏高价值：本科 1 篇论文/几个 repo，无重复可累积，价值需判别而非计数。③**三层防线防 LLM 误判**：(a)拉取只提结构化事实，LLM 不参与判断；(b)分级用规则表（论文 venue→CCF 白名单查表；仓库质量信号规则：fork 降权/commit<10 课程作业概率/持续 commit 是活跃证据/star 仅参考）——LLM 只把事实+分级归纳成主张文本，不做价值判断；(c)用户校对兜底（卡片摆结构化事实，人拦误判）。④作品证据主张直通 verified（公开可验证），与浏览信号（trial 攒证据）形成 D20 verified/trial 分离的两半 |
| D24 | 信号理论视角（理论基础） | 引入 Spence 信号理论（1973 QJE + 2002 AER 回顾）：①信号成本与能力负相关才有分离均衡——**高成本低造假的信号才是好信号**：一作顶会论文/持续 commit 的原创 repo 信号成本高（低能力者难以伪造）→ 强信号；浏览行为/关键词成本低 → 弱信号（trial 合理）。②credential inflation 教训：当信号成本趋同（人人都有学位/八股项目），信号失去分离力 → 雇主转向直接技能检验——我们的匹配应重视"直接可验证产出"（repo 代码/论文）胜过"资质声称"。③求职者是信号发送方：TalentForge 帮用户识别自己哪些信号强/弱/缺失 → 补短板建议本质是"信号组合优化"。④signal vs index 区分：不可改变的（学校/专业）是 index，可投资的（论文/项目/技能）是 signal——决策建议应聚焦 signal 侧。落点：M4 作品源分级规则表 + 匹配层的信号强度权重 + 补短板建议生成 |
| D25 | 平台源架构调整：扩展采集为反爬平台唯一通道 | ①证据链：Boss 服务器侧方案全灭（IP 段风控 code 35、disable-devtool 关页面、二维码投毒、__zp_stoken__ 绑定页面环境 QR 登录拿不到——见 boss-cli #16/#21/#27、mcp-bosszp 账号封禁、Agent-Reach #56）；同类存活项目（eatmoreduck 912★、bot66 PR、Snseam 89★）共性=用户真实浏览器干活。②新架构：反爬平台（Boss/B站/知乎及未来扩展）一律走浏览器扩展 content script 在页面内采集/fetch API（同源 cookie/stoken 自然有效、明文薪资、零对抗零封号面）；公开 API 平台（GitHub/Gitee/arXiv，M4）走服务器直连。③BossScraper/qr_login 降级：服务器侧抓取仅保留 offline-file 模式（测试/演示），报告管线改为消费库内岗位。④扩展=通用客户端采集器：一个扩展 N 平台适配器，新增平台=新增 content script + manifest 域名 |
| D26 | GitHub 双用途定调：作品信号 + 信号投资循环 | ①用途一（作品源，M5 在建）：拉取用户自己的 repo/论文 → 结构化事实 + D24 规则分级 → verified 主张入画像/简历——"向雇主证明你"。②用途二 = 信号投资循环（gap→项目推荐）：工作台 gap（如"缺 K8s 实践"）→ GitHub search 按_gap 关键词搜优质 repo（规则筛：活跃度/贡献门槛/stars 仅参考）→ 生成"信号投资建议"卡片（参与此项目可低成本积累强信号）——推荐即"找感兴趣的项目"；用户参与后由用途一下轮拉取捕获新强信号，gap 闭环。③弱信号采集（star/watch 浏览）不单独建设——推荐结果已覆盖发现需求，参与行为走作品源强信号；扩展适配器留 backlog。落点：M5 收尾后立项 gap→推荐管线 |
| D27 | R1 修订：fork 按增量衡量（用户实证反馈） | ①原 R1"is_fork→weak 一票否决"误判毕设类仓库（用户举证 Liber1917/vitfly：fork 基础框架后 300 增量 commits/81 天持续演进——恰恰是高成本投入的强信号）；②新规则：fork 后零增量→weak（收藏/抄壳），有增量则切换到增量度量（own_commits/own_span_days）走 R2/R3 正常分级；③R3b 新增：own_commits≥100 且 own_span≥60 天→strong（高密度持续投入）；④度量方法：since=fork(created_at) 的提交统计，不用 author 过滤——实测毕设仓库 email=user@vitfly 未关联 GitHub 账号只匹配 2/300 严重漏算；⑤已知局限（记录）：增量含 merge 上游提交（保守高估）、commit 质量/空提交不衡量——规则保守可解释 + D23 防线 c 用户校对兜底 |
| D28 | 简历产出页命名分域：/cv | 产出页路由由 /resume 改为 /cv，消除与 GSD /gsd-resume-work（会话恢复命令）的语义混淆——聊天斜杠命令与浏览器 URL 虽不同域，但文档与对话提及"resume"时歧义真实存在；/cv 为简历国际通用叫法，短且无冲突。旧 /resume 路径保留 302 跳转（书签友好）。/api/profile/resume-review（简历文件校对）不改——其语义本就是"审阅 resume 文件"，与 GSD 命令无混淆 |
| D29 | 内容探针：LLM 证据分类补规则盲区（防线 b 有据修订） | ①盲区实证（用户举证 Embedded_training_IEST 35 commits/717天被 R3 判 strong，实为培训资料收集库）；②三层设计：strong 候选补采便宜证据（README 头 2000 字+顶层条目+最近 5 条提交）→ LLM 五分类（engineering/research/documentation/coursework/mixed）必须引用原文证据 → 规则映射：documentation 封顶 normal（R9），LLM 永不直接定级；③探针任何失败返回 None 不阻断采集；④真机校准：Embedded_training_IEST/documentation→降 normal（0.92 置信）、intellistanz/documentation→降 normal（探针额外抓出的误判）、vitfly/research 保持 strong、Tiao2024/engineering 保持 strong——strong 7→5 与用户判断一致；⑤证据随 facts.content_probe 上画像卡展示（防线 c 用户校对兜底不变）；coursework/mixed 不自动降级（低置信边缘交用户裁决） |
| D30 | 采集模式分级 manual/assist/auto（按平台风控强度与采集语义分档） | ①动因：用户裁决"Boss 要人在场主动浏览，其他平台可尝试自动访问"——对 spec-m2b 排除项（任务派发系统不做）的**定向修订**，非整体推翻；②三档：manual=现状被动 tap（B站/知乎）；assist=用户在场+页内拟人辅助，人启停、采集语义不变（Boss：滚动脉冲开关）；auto=后台任务派发无人访问（仅限风控弱×岗位类**事实**采集）；③双红线：**行为类平台（bilibili/zhihu）永不 auto**——其采集语义是用户显示性行为（D6/O1 画像自长），自动访问=伪造行为数据，污染的是画像的认识论基础，比风控更根本；**Boss 永不 auto**（D25 账号封禁证据链 + 用户裁决）；④任务子系统最小化：SQLite collection_tasks + enqueue/claim/report 三端点 + 扩展 service-worker 复用 alarms 轮询——只做"访问页面"一种任务原语，不做 OpenBiliClaw task multiplex 全套（动作编排/backfill/WS 推送均不做）；⑤护栏：每任务停留预算（拟人抖动、上限 30s）、并发 tab=1、平台日配额、风控信号检测→中止+平台冷却+落库展示（绝不绕过验证码，沿 D25）、policy 全局 kill switch；⑥立场承认：auto 弱化"零对抗"——自动化访问模式本身即风控检测对象，故仅用于低防御目标；账号安全 > 采集覆盖 |

## 悬置问题（单独探讨，触发时机见各条）

> 编号说明：O3 从未启用——`git log -S "O3" --all -- docs/` 无任何命中，O1→O2→O4 跳号自初始提交（0e1bbc5）即如此，非中途废弃。

### O1 — 画像层深度：如何移植 OpenBiliClaw 灵魂机制
- 状态：accepted（D19 收口，方案C+α机制）。以下候选 A/B/C 为研讨期历史描述，现状以 D19 与 deliberations/O1-profile-depth.md §7 为准。
- 背景：OpenBiliClaw 五层自进化（事件→偏好→觉察→洞察→灵魂）依赖海量内容消费事件；求职域信号稀疏 1–2 个数量级，上三层可能空转。
- 候选：
  - A. 完整五层（领域重写 taxonomy / prompts / 字段）
  - B. 三层（事件 + 偏好 + 职业自我认知，显式为主 + 稀疏推断）
  - C. 两层最简（显式画像 + 事件增量，不做自进化）
- 关联：与 O2 是同一问题的两面（「人的模型」+「怎么拿它匹配」）。O2 的偏好/效用模型方向可能反哺 O1 的答案。
- 硬约束（D10 派生）：无论选 A/B/C，人的模型必须同时容纳**人格叙事轨**（身份/价值观/深层驱动）+ **偏好/效用轨**（岗位属性偏好序）。五层中 事件→偏好 ≈ 效用轨，觉察→洞察→灵魂 ≈ 叙事轨。
- 新增维度（D12 派生）：双轨之外还需「结构位置」（社会关系总和）+ 独立「场域」建模——超出 OpenBiliClaw 五层，无上游可移植，需全新设计。
- 触发时机：soul 里程碑规划前。

### O2 — 匹配 × 胜任力桥接：量化方法
- 状态：accepted（2026-08-21）——D20 收口，研讨工件 docs/deliberations/O2-resume-packaging.md:3（"状态：accepted … 2026-08-21"）。以下方向列表为研讨期历史描述。
- 背景：TalentModel-skill 未经理论审视（6 维度、禁定量均为经验约束），需引入理论根基，不能直接采纳。
- 方向（用户提出，待深入）：
  - 经济学/匹配理论中的偏好：单边偏好建模 + 考虑集选择（无需双边 Gale-Shapley）
  - 显示性偏好（Revealed Preference）：行为流（投/拒/接 offer）反推岗位属性偏好序，与 D6 咬合
  - 序数打分（ordinal / pairwise / learning-to-rank）而非基数 0–100
  - 学界量表（BARS / Likert）给胜任力维度补理论根基；完整心理计量（信效度）MVP 过度
- 硬约束（D10 派生）：匹配是**二维**评估——市场契合（胜任力满足 JD）+ 成长契合（岗位推进个人叙事/锻造轨迹），非一维分数。
- 触发时机：matcher 里程碑规划前。

### O4 — 岗位源范围与只读抓取验收口径
- 状态：已收口。三重裁决依据：①D22①——M2a 只做 Boss 单源（牛客/校招官网未立项）；②D25②——反爬平台一律走浏览器扩展 content script，服务器侧抓取链路移除（commit 0174622）；③验收口径达成——spec-m2a 交付范围⑥"登录授权下抓 ≥20 条"由扩展路线兑现（docs/research/m4-acceptance.md「D25 补充验收」真机一次入库 30 条，2026-08-23）。
- 原问题：Boss 直聘 + 牛客 + 校招官网？与只读抓取验收口径。

## D → spec → 模块 追溯索引

> 事后补建（2026-08-30），M8–M10 三个无 spec 里程碑见 docs/spec-m8-m10-retro.md。spec 覆盖缺口如实标注；模块指 talentforge/ 下代码（前端 web/、插件 extension/ 另计）。

| # | 主题 | spec | 代码模块 |
|---|---|---|---|
| D1 | 核心定位 | spec-mvp-design.md §0/§2 | —（全局定位，无独立模块） |
| D2 | 自动投递 | spec-mvp-design.md §2；spec-m3-web.md §6 | —（维持不做） |
| D3 | 目标用户 | spec-mvp-design.md §1 | — |
| D4 | MVP 垂直切片 | spec-mvp-design.md §10 | 全链路（M0–M4） |
| D5 | 闭环形态 | spec-mvp-design.md §4 | report/generate.py + feedback/ |
| D6 | 画像输入显式优先 | spec-m1 交付范围④ | profile/engine.py |
| D7 | CLI + Web + 插件 | spec-m2b-extension.md；spec-m3-web.md | cli.py；api/ + web/；extension/ |
| D8 | 技术栈 | spec-mvp-design.md §12 | —（全局约束） |
| D9 | 三元决策+可解释链 | spec-mvp-design.md §6.1 | decision/verdict.py |
| D10 | 双轨人的模型 | spec-mvp-design.md §0/§5 | domain/profile.py |
| D11 | 反思性决策对话 | spec-m3-web.md §1 | api/routes_chat.py + web/js/views/chat.js |
| D12 | 双轨结构化+场域 | spec-mvp-design.md §3.1；spec-m2a 交付范围③ | field/risks.py |
| D13 | 提问式方法 | spec-m3-web.md §1；spec-m7-explorer.md | api/routes_chat.py；explore/engine.py |
| D14 | 批判层 MVP 内置 | spec-mvp-design.md §6.3；spec-m2a 交付范围③ | field/risks.py（结构性风险库） |
| D15 | 稳定核心+可拓展外围 | spec-mvp-design.md §3.2 | protocols.py；decision/；feedback/ |
| D16 | O1 画像机制决议 | deliberations/O1-profile-depth.md §7；spec-m1 | profile/（engine/pipeline）+ domain/profile.py |
| D17 | 八格结构位置 | spec-m1 交付范围① | domain/profile.py（StructuralPosition） |
| D18 | 词表护栏+用户确认 | spec-m1 交付范围② | profile/vocab.py |
| D19 | O1 收口 | deliberations/O1-profile-depth.md | 落点同 D16–D18 |
| D20 | O2 简历包装决议 | deliberations/O2-resume-packaging.md；spec-m5 §1.3 | profile/engine.py（claims 状态机）+ feedback/ |
| D21 | 校对交互全走 Web | spec-m3-web.md §3 | api/routes_profile.py + web/ |
| D22 | M2 方案定稿 | spec-m2a-jobs.md；spec-m2b-extension.md | sources/ + field/ + matcher/ + report/ + extension/ |
| D23 | 作品源三层防线 | spec-m5-work-sources.md | sources/work_sources.py + work/store.py + api/routes_work.py |
| D24 | 信号理论 | spec-m5 §2；spec-m6；spec-m7 | sources/work_grading.py |
| D25 | 扩展唯一采集通道 | 无独立 spec——验收记录 docs/research/m4-acceptance.md「D25 补充验收」+ 新源适配指南 docs/adapting-new-sources.md | extension/src/content/boss.ts + api/routes_jobs.py + report/generate.py（commit 5a531fa / 0174622） |
| D26 | GitHub 双用途 | spec-m6-signal-investment.md | sources/project_suggest.py + api/routes_suggest.py |
| D27 | fork 按增量衡量 | spec-m5 §2 R1（spec 正文未回写，现行规则以代码为准） | sources/work_grading.py（commit 5dcfbf4） |
| D28 | /cv 命名分域 | spec-m5 §6（已随 commit 70553d5 更新） | api/routes_resume.py + /cv 页 |
| D29 | 内容探针 | spec-m5 §2 防线 b（spec 正文未回写，现行规则以代码为准） | sources/content_probe.py + api/routes_work.py（commit f4b0da9） |
| D30 | 采集模式分级 | spec-m11-graded-collection.md | sources/collection_policy.py + api/routes_tasks.py + storage/db.py（collection_tasks）+ extension/src/background/task_runner.ts + content/boss.ts（assist 开关）+ content/{shixiseng,zhaopin,zhaopin-main}.ts + shared/jobs_report.ts（SW 中转，兼修 PNA/Origin） |
