# M2a 规格 — Boss 岗位链路垂直切片

> ⚠️ 修订记录：本 spec 的采集/验收口径已被 D25（扩展为唯一采集通道）部分修订——服务器侧抓取（BossScraper/playwright/cookie 链路）已移除，岗位采集走浏览器扩展 content script，报告管线消费库内岗位（report/generate.py）。失效验收项以下方 ✅/❌ 注记标明现状。

> 依据：spec-mvp-design.md §10 + D22 + m2-boss-recon.md（路线选择与坑清单）+ O1a 残余（场域最小版）。

## 交付范围

1. ❌ **Boss 抓取器**（sources/boss.py）：改造 jobclaw BossScraper——修三坑（城市码表、卡片选择器回退链、薪资统一为 min_annual 年薪口径）；加翻页（页间 5-10s 随机延迟，单 run ≤3 页）；验证码检测（移植 jobclaw captcha.py 的 9 选择器+4 关键词，纯函数）；登录复用 jobclaw cookie 机制（env cookie > ~/.jobclaw/cookies/boss.json）。

   > ❌ 注记（2026-08，D25）：本项已失效——commit 0174622 移除服务器侧抓取链路，sources/boss.py 仅存 `--offline-file` 演示/测试模式；线上岗位采集改走浏览器扩展 extension/src/content/boss.ts（wapi 通道），经 POST /api/jobs/batch（talentforge/api/routes_jobs.py:75，D25 入库通道）落库。
2. **Job 归一化 + 存储**：SQLite（storage/ 首个真实表：jobs，含去重键 job_url、risk_keys 提取——JD 文本里扫"996/大小周/竞业"等关键词入 structural 风险标记）。
3. **场域最小版**（field/minimal.py）：结构性风险信号库——硬编码 ~10 条风险（996/大小周/无社保/竞业限制/无偿加班…），每条带"为什么是剥削"的政治经济学解释文案（供决策卡展示）；从 Job.risk_keys + JD 文本扫描命中。
4. **匹配粗版**（matcher/coarse.py）：LLM 单跳——输入 Profile（含 verified/unverified claims + 八格）+ Job + 风险命中，输出 FitLevel(market/growth) + reasoning + matched/missing skills。市场契合看硬字段（verified 技能 vs JD 要求），成长契合看叙事轨（deep_drives vs 岗位方向）。
5. **决策报告命令**：`talentforge report --profile <path> --query "后端工程师" --city 深圳`——抓取→归一化→逐岗匹配→decide()→输出 JSON 报告（verdict + 可解释链骨架 + 风险警示）。
6. ✅ **验收**：登录授权下抓 ≥20 条（spec O4 口径）；报告对 ≥10 岗位给出三元决策。

   > ✅ 注记（2026-08，D25）：≥20 条门槛已由扩展路线达成——docs/research/m4-acceptance.md「D25 补充验收」（2026-08-23 真机）wapi 通道一次入库 30 条，超过门槛；「登录授权下」口径随 D25 失效（采集在用户自己浏览器内完成，天然登录态、无 cookie 配置步骤）。O4 状态见 design-decisions.md 悬置问题节（已收口）。

## 不在本里程碑

- 插件内容采集（M2b：核心管道 + B站/知乎适配）
- 序数偏好精排（匹配细版）、显示性偏好回流消费
- 格 5/8 市场侧估算（岗位数据量足够后再做——本里程碑只做风险信号库）
- Web 界面（M3）

## 测试策略

抓取器选择器/城市码/薪资解析纯函数单测（HTML fixture）；风险命中纯函数单测；匹配器假 LLM 测试；决策报告集成测试（mock 抓取器+假 LLM 端到端）；真实抓取验收手动跑一次（用户授权 cookie）。
