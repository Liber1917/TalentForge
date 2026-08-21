# M2 前置侦察 — Boss 直聘抓取的现实约束与路线选择

> 证据来源：/home/jobclaw 全量精读（本会话第一阶段，全部带 file:line）；纯代码研究，未发任何真实请求到 zhipin.com。

## 1. jobclaw 的 BossScraper 怎么工作（scraper/boss.py，133 行）

- **搜索 URL 构造**（boss.py:60-62）：`https://www.zhipin.com/web/geek/job?query={query}&city=101280600`——**city 参数硬编码 `101280600`（深圳）**，location 只是附加参数；这是 jobclaw 未完成的痕迹，M2 必须做成城市码表。
- **等待策略**：`wait_until="networkidle"`，30s 超时（boss.py:66）——Boss 是重 SPA，networkidle 是必要的但慢。
- **卡片选择器**（boss.py:67）：单点 `.job-card-wrapper`——**无回退链**，Boss 改版即断（对比 applier 侧有 5-6 个回退选择器，scraper 侧明显薄弱）。
- **字段提取**（boss.py:71-83）：每卡内 `.job-name`/`.company-name a`/`.salary`/`.job-card-left a`(href)/`.tag-list span`/`.job-card-desc`——一次 query_selector_all 后逐卡 try/except，坏卡跳过（boss.py:99-100）。
- **薪资解析**（boss.py:112-133）：正则 `(\d+)-(\d+)K` + `(\d+)薪` 奖金月数，**默认 12 薪**；`25-50K·16薪` → min=25000×16/max=50000×16（**注意：这是把月薪乘成"年薪"，与 SalaryRange.min_annual 语义一致但 jobclaw 的 Profile 侧按月配，两处语义有错位——TalentForge 引入时须统一**）。
- **翻页**：**没有**。单页 `.job-card-wrapper` 全量截取 + `[:limit]`（boss.py:69）。M2 若要 ≥50 条必须加翻页/多 query。

## 2. 反爬信号清单（Boss 侧实证）

- **验证码检测**（applier/captcha.py:12-20）：9 个选择器（`#captcha`/`.slide-verify`/`.geetest_panel`/`.captcha-wrapper`/`[class*='verify']`/`[class*='captcha']`/`div.dialog-container:has(canvas)`）+ 4 个关键词（"请完成安全验证"/"滑动验证"/"图形验证"/"安全检测"，captcha.py:41）。
- **投递侧的日限信号**（applier/boss.py:56-59）：页面文本"今日沟通人数已达上限/今日投递次数已用完/今天的机会已用完"——说明 Boss 有频控，scraper 侧同样会触发。
- **登录墙**：无 cookie 时搜索页大概率跳 `/web/user` 登录（browser_login.py boss 条目 `check_redirect_pattern: "/web/user"`，:25-30）。
- **关键 cookie**（browser_login.py:28）：`wt2`/`wbg`/`wd_guid`——`wt2` 是主会话凭证（cookie_manager.py:22 也是 `wt2`）。
- **README 防封清单**：随机延迟 3-8s（可配）、日上限默认 100、僵尸岗过滤、JSON 防重投历史——这些是**投递侧**的；抓取侧 jobclaw 只靠"单页一次+超时"天然低频。

## 3. 三条路线对比

| | A. Playwright 后端抓（jobclaw 路线） | B. 插件真实会话 DOM 采集（OpenBiliClaw 路线，D7） | C. 混合：M2 用 A 跑通，M3+ 迁 B |
|---|---|---|---|
| 工程量 | **小**（jobclaw boss.py 133 行可直接改造；Python 侧无前端工程） | **大**（content script + MV3 工程 + 与后端事件契约；OpenBiliClaw 单平台适配面见 m2-extension-recon.md） | 中（先 A 后 B，A 的归一化层可复用） |
| 反爬风险 | **高**（Playwright 自动化指纹；Boss 对无头/自动化有 WAF+验证码；需验证码暂停+人工介入） | **低**（真实浏览器会话、真实指纹、用户自己登录） | 前期高后期低 |
| 登录成本 | cookie 注入（jobclaw login 流程已验证） | 用户自然登录，零额外成本 | 同左 |
| 采集频率 | 受风控约束，需保守 | 用户浏览自然产生，无额外频率 | — |
| 与 O1 内容采集的关系 | **零复用**（内容采集走插件，岗位走 Playwright = 两套采集栈） | **同一套插件栈**（岗位卡片=另一种 content script 事件） | 最终统一到插件 |
| M2 里程碑风险 | 低工程量、快出垂直切片 | 8 平台内容采集 + Boss 岗位一起压进 M2，工程失控风险真实存在 | 分期释放风险 |

## 4. 推荐：路线 C（混合），M2 内分两步

1. **M2a：Playwright 岗位抓取跑通垂直切片**（jobclaw 改造：city 码表 + 卡片回退选择器 + 翻页 + 验证码暂停人工），归一化进 Job schema——**快速验证匹配/决策链路有真数据**，反爬风险用"低频 + 登录授权 + 验证码暂停"控制（spec §8 合规红线本来就要求这样）。
2. **M2b：插件栈落地时（内容采集 8 平台）顺手把 Boss 岗位采集迁进插件**（用户浏览岗位列表页 = 采集事件），Playwright 降级为离线导入兜底。

理由：(a) 匹配/决策链路不应等插件工程；(b) O1 已定插件路线是终态，C 不违背 D7 只是排期；(c) jobclaw 代码 MIT 且已验证可跑通登录+抓取，改造面小。

## 5. M2 落地要点（从本侦察直接导出）

- 城市码表（jobclaw 硬编码深圳是已知坑）
- 卡片选择器回退链（学 applier 侧的多选回退模式）
- 薪资语义统一（月薪 vs 年薪，SalaryRange.min_annual 口径）
- 翻页/多 query 凑 ≥20 条验收（spec O4 口径）
- 验证码检测复用 jobclaw 9 选择器+4 关键词（captcha.py 全套，纯函数可移植）
- 频控：默认单次 run ≤3 页、页间 5-10s 随机延迟（比 jobclaw 投递侧更保守）
