# TalentForge Web 设计系统

## 0. Research Log

- Embedded refs: shortlisted [claude.md / notion.md / intercom.md] → picked `taste-skill.md`(Layer A,trust-first 分支) + `claude.md`(Layer B) — claude 的"温暖纸面+衬线权威+terracotta"与"批判意识助产士"的产品气质同构（安静智识陪伴，非工具冰冷）
- Lazyweb: 未跑（本机 curl lazyweb.com 需匿名 token 配方，时间盒内省略——以 claude.md 现成 token 集为基准）
- Imagen drafts: 未生成（无 imagegen 工具链；用 claude.md token + 手绘风原则替代）
- Skipped lanes: lazyweb / imagen — 工具原因；嵌入参考已覆盖色彩/字体/组件/深度/动效全部 token 面

## 1. Atmosphere & Identity

**一间安静的书房，坐着一位懂你的求职顾问。** 产品是"锻造台"而非"投递机器"：纸面般的暖色画布、衬线标题的出版物质感、terracotta 只在关键时刻出现（投递决策/确认按钮）。**签名记忆点是"证据链展开"**——任何画像主张、决策理由、风险警示都能层层展开到原始证据（你浏览过的内容/你说过的话/JD 原文），像翻开顾问的笔记本。深色模式 = "夜间书房"（暖炭色，非冷黑）。

Dials: VARIANCE 4（信任优先，克制）/ MOTION 3（服务信息，不炫技）/ DENSITY 5（对话流+工作台双密度）。

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/primary | --surface-primary | #f5f4ed (Parchment) | #141413 | 页面背景 |
| Surface/secondary | --surface-secondary | #faf9f5 (Ivory) | #30302e | 卡片、面板 |
| Surface/elevated | --surface-elevated | #ffffff | #3d3d3a | 弹层、悬浮卡 |
| Surface/sand | --surface-sand | #e8e6dc | #46453f | 次级按钮、输入框底 |
| Text/primary | --text-primary | #141413 | #faf9f5 | 标题、正文 |
| Text/secondary | --text-secondary | #5e5d59 (Olive Gray) | #b0aea5 | 次级文字 |
| Text/tertiary | --text-tertiary | #87867f | #87867f | 元数据、脚注 |
| Accent/primary | --accent | #c96442 (Terracotta) | #d97757 (Coral) | 主 CTA、verdict=投、确认 |
| Accent/soft | --accent-soft | #f0e0d8 | #3a2e28 | accent 背景 tint |
| Border/subtle | --border-subtle | #f0eee6 | #30302e | 卡片边 |
| Border/strong | --border-strong | #e8e6dc | #46453f | 分隔、强调边 |
| Semantic/hold | --hold | #a88242 (琥珀) | #c2a05e | verdict=观望 |
| Semantic/skip | --skip | #87867f (Stone) | #87867f | verdict=不投（中性，不羞辱） |
| Semantic/risk | --risk | #b53333 (暖红) | #d97757 | 风险警示（暖红非亮红） |
| Semantic/risk-bg | --risk-bg | #f7e8e4 | #33241f | 风险卡背景 tint |
| Semantic/ok | --ok | #6b8f71 ( muted 绿) | #89a89b | 确认/转正、证据链锚点 |

**三值 verdict 色彩语义**（核心决策）：投=terracotta（行动暖色）· 观望=琥珀（暂停思考）· 不投=stone 灰（中性搁置，**不用红色**——不投不是失败，是策略性放弃）。

**风险警示**：暖红 #b53333 + risk-bg tint，永远配"为什么"文案（D13 知情非恐吓）。

### 对比度
- text-primary on surface-primary: 13.2:1 ✓；text-secondary on ivory: 5.9:1 ✓（WCAG AA）
- accent 按钮文字用 #faf9f5 on #c96442: 4.6:1 ✓（大字号按钮 AA）

## 3. Typography

- **标题/衬线**: `Georgia, "Songti SC", "Noto Serif SC", serif`（Anthropic Serif 替身；中文衬线用宋体系）——所有页面标题、卡片标题、verdict 字样
- **正文/UI**: `system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`——按钮、标签、导航、正文
- **等宽（证据/ID）**: `ui-monospace, "SF Mono", Consolas, monospace`——event_id、BV号、日期戳

| Role | Font | Size | Weight | LH |
|------|------|------|--------|-----|
| Page Title | serif | 28px | 500 | 1.2 |
| Card Title | serif | 20px | 500 | 1.3 |
| Body | sans | 16px | 400 | 1.6（编辑式宽松） |
| Body Small | sans | 14px | 400 | 1.5 |
| Caption/Meta | sans | 12px | 400 | 1.43（letter-spacing .12px） |
| Verdict 字样 | serif | 15px | 500 | 1 |
| Overline 标签 | sans | 10px | 500 | 1.6（uppercase, ls .5px） |
| Mono 证据 | mono | 13px | 400 | 1.5 |

原则：衬线只到 weight 500（出版感）；正文 1.6 行高（书房阅读节奏）；中文场景标题用宋体系衬线保持"出版物"质感。

## 4. Spacing & Layout

- Base 8px；scale: 4/8/12/16/20/24/32/48/80
- 卡片内边距 24px；区块纵向 48-80px（编辑式呼吸）
- Radius: 卡 12px / 按钮+输入 12px / 内嵌元素 8px / 大容器 16px / 标签 pill
- 布局：对话页单列居中 max-width 720px（阅读最优）；工作台/画像双栏（列表 2fr + 详情 3fr，<768px 折叠单列+抽屉）
- 容器 max-width 1200px

## 5. Primitives（组件原语——实现前先过 showcase）

| 原语 | 状态 | 说明 |
|---|---|---|
| **Btn** | default/hover/active/disabled/focus-visible | 4 变体：primary(Terracotta)/secondary(Sand)/ghost/danger(risk) |
| **Card** | default/hover(仅可点卡片)/embedded(对话内) | Ivory 底 + border-subtle 1px + 12px 圆角；embedded 版窄边距 |
| **VerdictBadge** | apply/hold/skip | pill；衬线字样；apply=terracotta 实底白字，hold=琥珀描边，skip=stone 描边 |
| **EvidenceChain** | collapsed/expanded/loading | 证据链锚点列表（mono 字号）；展开显示 证据类型 icon+来源+时间；锚点行点击滚动高亮 |
| **ClaimCard** | trial/active/archived + confirming/refuting | 画像主张卡：文本+状态 pill+证据链+三操作（确认/驳回/聊聊） |
| **RiskNote** | collapsed/expanded | 风险标签+一句话；展开="为什么是风险"政治经济学文案（risk-bg tint） |
| **ChatBubble** | user/assistant/card-host | assistant 泡含卡片时无气泡边框（卡片即消息）；user 右对齐 sand 底 |
| **ReflectivePrompt** | idle/answered/dismissed | 反思问题块：衬线斜体提问+可选输入框 |
| **Field/Table** | 行业标准 | 工作台岗位列表：紧凑密度行，verdict badge 前置 |
| **Drawer** | open/closed | 移动端详情抽屉 |

## 6. Motion

- 原则：动画只服务信息（D13 不炫技）——展开/收起 160ms ease-out；verdict 变化 240ms（确认转正的仪式感一瞬）；卡片展开用 grid-template-rows 过渡
- 证据链展开：高度过渡 + 锚点行背景闪烁一次（ok 色 600ms 淡出）
- 全部尊重 `prefers-reduced-motion`（直接跳终态）
- 禁：无限循环装饰动画、非交互元素 hover 动效、布局属性动画（只用 transform/opacity/height）

## 7. Accessibility

- 对比度全 AA（上文已验）；verdict 不只靠颜色（badge 带文字）
- 证据链展开用 `<details>` 语义或 aria-expanded；对话流 aria-live="polite"
- 键盘：卡片可 focus（tabindex=0），Enter 展开；三操作按钮是真 button
- 触控目标 ≥44px；focus ring 用 --ok 绿（可见于暖底）

## 8. Responsive

| 断点 | 布局 |
|---|---|
| <640 | 单列；工作台列表→点击进 Drawer 详情；顶栏折叠为 图标+待定池数 |
| 640-1024 | 对话页不变；工作台单栏列表+详情下推 |
| >1024 | 工作台双栏；画像三栏轨并排（<1024 纵向 tab 切换） |

## 9. 接受债务（Accepted Debt）

- M3 首版不做自定义插画系统（用 verdict badge+证据链锚点作为视觉记忆点替代有机插画）；插画后置
- 中文衬线在 Windows 非高分屏渲染发虚——接受宋体 fallback，后期可换 web font（需 subset 加载）
- 暗色模式首版可后置（token 双列已定义，实现按 token 写即可切换）
