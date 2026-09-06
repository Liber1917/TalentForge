# M12 规格 — 新手引导模块（演示沙箱）

> 决策依据：**D31**（演示沙箱三红线）。复用 M3 前端假数据（LOCAL_FIXTURE_*）做引导素材；
> 用户可**随时打开/重放**引导；假数据**永不污染**用户真实数据（SQLite/画像文件/localStorage 真实开关）。

## 地基事实（为什么这个方案几乎免费）

后端不存在任何 `/api/fixtures` 路由（app.py 全文与 14 个 router 均无）——前端假数据是
视图模块内嵌的 `LOCAL_FIXTURE_*`（jobs.js/chat.js 等），fixture 模式的交互全部客户端
mock。因此"演示数据写坏真库"在物理上不可能发生；设计只需守住三个软面：

1. **后端契约**：永不注册 `/api/fixtures/*` 路由（防御测试钉死，GET 也不加——静态伺服即可）；
2. **localStorage 隔离**：引导状态只用 `tf_tour_*` 命名空间；进入引导时保存 `tf_real`、退出时还原；
3. **认知横幅**：引导全程顶部横幅"演示数据——不会写入你的真实数据"（防认知污染）。

## 交互设计

### 六步引导流（每步 = 导航 + spotlight + 讲解卡）

| 步 | 视图 | spotlight 目标 | 讲解要点 |
|---|---|---|---|
| 1 欢迎 | #/chat | 对话输入区 | TalentForge 是什么：陪伴式求职决策，不是简历投递器 |
| 2 决策卡 | #/chat | 演示 DecisionCard | 三态 verdict（投/观望/跳过）+ 理由链 + 风险标签——每一步可解释 |
| 3 工作台 | #/jobs | 三态列表 + 筛选 | apply/hold/skip 全景；点卡片看详情（gap 补短板） |
| 4 画像 | #/profile | 八格结构位置 | 叙事双轨 + 结构位置：系统从对话和反馈里"认识你"，你随时校对 |
| 5 采集 | #/sources | 平台源卡 | 岗位/行为数据从浏览器扩展来（你在 Boss/B站/知乎正常浏览即采集） |
| 6 切真 | 当前 | 横幅本身 | 现在看到的全是演示数据；配置 LLM + 装扩展后切到真实模式（?real=1） |

- 步骤卡固定右下角（不遮内容），含"上一步/下一步/跳过引导"；Esc = 退出。
- spotlight：目标元素加高亮描边 + 呼吸光晕，其余区域压暗（半透明遮罩挖洞实现）。

### 入口（随时可开，可重放）

1. **首启自动建议**：`/api/onboarding/status` 四维全 false 且 `localStorage.tf_tour_done != "1"`
   → 对话空态额外渲染一张"看 2 分钟新手引导"卡片（点击进入；不再显示）。
2. **常驻入口**：顶栏状态区新增"新手引导"按钮（任何视图可见）。
3. 引导完成/跳过 → `tf_tour_done = "1"`（只影响自动建议，不影响手动重开）。

### 沙箱进入/退出语义

- 进入：记录 `_tf_tour_prev_real`（tf_real 原值）→ 强制 fixture 模式（本次会话内
  api 层 override，见交付范围）→ 挂横幅 → 从第 1 步开始。
- 退出（完成/跳过/Esc/关闭）：移除横幅与 spotlight → 还原 `tf_real` 原值 → 视图恢复真实模式渲染。
- 引导期间的一切交互均为客户端 mock（现有 fixture 机制），无网络写入。

## 交付范围

1. **web/js/tour.js**（新模块，导出 `TalentForgeTour`）：
   - 纯逻辑核心（可 node --test）：步骤表、状态机（start/next/prev/goTo/stop）、
     沙箱开关（enterSandbox/exitSandbox：tf_real 保存/还原 + `tf_tour_*` 命名空间）；
   - DOM 装配：横幅、步骤卡、spotlight（`data-tf-tour-target` 属性定位，找不到目标时降级为居中卡不 spotlight）；
   - 与路由协作：步骤切换时 `location.hash` 导航到对应视图。
2. **web/js/api.js**（微扩）：暴露 `setFixtureOverride(bool)`——tour 沙箱用；
   请求 BASE 在 override 时强制 `/api/fixtures` 前缀（内存 flag，不落 storage）。
3. **web/index.html**：顶栏"新手引导"按钮 + tour.css 引入；**web/css/tour.css**（新）。
4. **web/js/views/chat.js**（微扩）：首启建议卡（读 onboarding/status + tf_tour_done）。
5. **tests/test_no_fixture_routes.py**（防御契约）：遍历 `create_app().routes`，
   断言无任何 path 以 `/api/fixtures` 开头的路由注册（含 GET——防止未来把演示数据做成真端点）。
6. **web/tests/tour.test.mjs**：vm 加载 tour.js（同 jobs.test.mjs 模式）——状态机流转、
   沙箱进入/退出对 tf_real 的保存还原、`tf_tour_*` 命名空间隔离、api override 生效与清除。

## 不做（M12 排除项）

- 不做多用户/多语言引导文案（单中文）；
- 不做进度持久化（每次进入从头开始——引导本身 2 分钟，重放即重看）；
- 不做移动端专门优化（按钮/卡片响应式即可，spotlight 桌面优先）；
- 不给 fixtures 加任何后端路由（D31 红线①）。

## 验收

1. **单元**：web/tests/tour.test.mjs 全绿（状态机/沙箱/命名空间）；pytest 防御测试绿；
   现有 web 130 测试零回归。✅（2026-09-06：pytest 393 绿（含 test_no_fixture_routes 2 例）、web 137 绿（含 tour 7 例），零回归）
2. **手动验收单**：`#/chat` 顶栏点"新手引导" → 横幅出现 + 第 1 步 → 六步走完 →
   横幅消失 + `tf_real` 还原 + 无 localStorage 泄漏（devtools 检查仅 `tf_tour_done` 新增）；
   中途 Esc 同样完整还原。
3. **污染审计**：引导全程 DevTools Network 面板零 POST；退出后真实数据视图不变。
   ✅（2026-09-06 真浏览器冒烟：按钮→横幅+步骤卡→步进→Esc 全清；localStorage 仅余
   tf_tour_done；USE_FIXTURES 还原默认；全程 15 个请求均为 GET，零 POST。步骤 2 的
   手动体感走查仍留给用户日常使用确认。）
