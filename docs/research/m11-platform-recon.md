# M11 平台侦察 — auto 候选五平台风控与结构摸底（拉勾/智联/猎聘/领英/实习僧）

> 日期：2026-09-02。方法：3 个 librarian 并行检索（~50 组中英文查询 + GitHub 仓库/issues/API 直读 + 关键页抓取）+ 本机数据中心 IP 直接 HTTP 探测（结构参考；住宅 IP + 真实登录态的实际表现以 OSS 存活项目证据校准）。评估场景：**D30 auto 档**——用户登录态、住宅 IP、单 inactive tab、停留 ≤30s、~20 次/天。

## 总表（结论先行）

| 平台 | 登录策略（浏览） | 风控强度 | 数据通道 | 2026 存活生态 | **auto 分档建议** |
|---|---|---|---|---|---|
| **智联** zhaopin.com | 匿名可搜（软墙，投递才登录） | **中**（EdgeOne 前门+极验守登录；浏览频控 40 次/10min） | XHR `fe-api.zhaopin.com`（无页面绑定 token） | **3 个 2026 活跃项目**，含同构扩展 | ✅ **auto（首选）** |
| **实习僧** shixiseng.com | 匿名列表+详情全开放（今日实测） | **弱—中**（字体反爬为主要防线） | SSR HTML（数字字体混淆） | 无 2024+ 项目（但技术路径 2023-12 实证） | ✅ **auto（次选，最省登录态）** |
| **猎聘** liepin.com | 无硬墙但匿名被降级（SPA 重定向），偶发登录弹窗/safe 验证 | **中—强**（点选验证码登录、__fid 指纹、搜索 60 次/15min） | XHR `api-c.liepin.com` + m 站 SSR 详情 | 425★ 浏览器扩展在做同样的事、零封禁报告 | ✅ **auto（条件：登录态+人机协作验证）** |
| **拉勾** lagou.com | 登录态产品 + 阿里云 WAF 前门 | 强（但无关紧要，见右） | XHR positionAjax + `__NEXT_DATA__` | 2026 集体弃坑 | ⛔ **不接入——平台已于 2026-05 自行申请破产** |
| **领英** linkedin.com | authwall 硬墙（大陆 451/封锁） | 强 | 游客职位端点可用 | JobSpy 4k★ 存活 | ⛔ **不接入——合规硬伤 + 大陆不可达 + 中国职位已清退** |

---

## 一、智联招聘 zhaopin.com — ✅ auto 首选

- **登录策略**：搜索列表与搜索 API 无硬登录墙；官方仅要求投递须登录。数据中心 IP 触发腾讯 EdgeOne "Security Verification"（`captcha.eo.gtimg.com`，今日实测），住宅 IP 真实浏览器通常透明放行。搜索 URL 用不透明 kw 编码（`kw01O00U80EG06G03F01N0`），URL 构造须从页面表单提交走（AgentMesh 已踩坑记录）。
- **风控**：登录链路极验滑块 100% 触发（微信扫码可绕开手动滑块）；`zp_token`(JWT ~7天) + `x-zp-client-id` 设备指纹；**无 Boss 式 `__zp_stoken__` 页面绑定 token**；频控：搜索 ~40 次/10min → 429 + 10min 冷却；同 IP 多账号 → 全站极验；headless 检测（webdriver+分辨率+字体）。**20 次/天比阈值低两个数量级。**
- **数据通道**：`GET fe-api.zhaopin.com/c/i/search/positions`（老 `/c/i/sou`）XHR JSON，普通 Cookie+浏览器头即可；新 v2 端点出现 `x-zp-fe-sign` 前端 AES 签名与 `security_id` 加密职位标识——**页面内被动嗅探模式不受影响**。
- **存活证据**：
  - [xixiluo95/zhaopin](https://github.com/xixiluo95/zhaopin)（119★，push 2026-06-14）——与本方案**完全同构**的 Chrome 扩展采集器；代码含风控状态机（cooldown 1h/4h/blocked_today）与"新标签页人工滑块→回来点已验证"协作流（证明真实浏览器+登录态仍偶发触发滑块，可控）
  - [jiyangnan/AgentMesh-JobAgent](https://github.com/jiyangnan/AgentMesh-JobAgent)（38★，push 今日）——智联 CDP 采集完整实现，`zhilian_login_required` 状态处理，夹具 2026-06-13 仍在更新
  - [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) 2026-04-20 [zhaopin.md 调研报告](https://github.com/can4hou6joeng4/boss-agent-cli/blob/master/docs/research/platforms/zhaopin.md)（端点/频控/指纹全表）
- **结论**：推荐。工程路径已被两个在维护项目验证；需预留滑块人工辅助 UI。

## 二、实习僧 shixiseng.com — ✅ auto 次选

- **登录策略**：**今日实测（2026-09-02，匿名+数据中心 IP）**：`/interns?k=Python` 列表页完整渲染（公司/职位/标签全量吐出）、`/intern/inn_xxx` 详情页完整渲染——**浏览无登录墙**（投递/沟通才需登录）。"实习僧强制登录"传闻在桌面 Web 未获证实（2021 CSDN、2023-12 cnblogs 两次独立爬取实践 + 今日实测均无墙）。
- **风控**：**弱—中**。主要防线是**字体反爬**（列表页数字用自定义 woff 映射——今日实测薪资数字位空缺即其痕迹；解码=下载 `/interns/iconfonts/file` 建 cmap，2023-12 课程设计实证可行）。2023-2026 无验证码/封号/限流公开报告。
- **数据通道**：SSR HTML（列表 `/interns?k=&p=`、详情 `/intern/inn_xxx`、公司 `/com/xxx`）+ wap 站并行；无页面绑定 token；历史移动端 API `iosapi.shixiseng.com`（2018 开放）现状未验。官方开放平台（open.shixiseng.com，MD5 签名）为商家侧，与 Web 通道无关。
- **存活证据**：无 2024+ 维护项目（MrhistWhite 3★/2019、sunjunee 40★/2017、librauee/Reptile 1750★/2021 教程含字体解密章）——平台受爬虫关注度低本身是弱防御的旁证。
- **残余不确定**：真实浏览器连续浏览 N 页后是否弹客户端登录框（静态探测不可见）——M11 真机验收时确认。
- **结论**：推荐。防御最弱、无需登录态即可采列表；数字字段需字体解码。

## 三、猎聘 liepin.com — ✅ auto（带条件）

- **登录策略**：无硬墙但**匿名被降级**——今日实测匿名 GET `/zhaopin/?key=Python` 返回 SEO 目录壳页（SPA 把匿名 `?key=` 重定向到通用列表，[AgentMesh liepin/collect.py](https://github.com/jiyangnan/AgentMesh-JobAgent/blob/main/src/jobagent/platforms/liepin/collect.py) 2026-09 注释证实）；代码显式处理 `liepin_login_required`、登录弹窗与 **`safe.liepin.com` 安全验证域**。详情页 `m.liepin.com/job/19x.shtml` SSR 对匿名开放（[job-pro 2026-07-11 复验](https://github.com/HA7CH/job-pro/blob/main/cli/src/liepin.ts)）。
- **风控**：中—强。登录用**点选验证码**；`__gc_id`(30天)+`__fid` 指纹+`x-liepin-token`(JWT 2h)；搜索频控 **~60 次/15min** → `errorCode 60001` 冷却 5-15min；WAF 对高频回 405；今日实测数据中心 IP 直调 API 得应用层 `-1400` 拒绝（浏览器上下文内不受影响）。封禁报告集中于**自动投递写操作**（[get_jobs #265, 2026-04](https://github.com/loks666/get_jobs/issues/265)），只读浏览无封禁案例。
- **数据通道**：XHR `POST api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job`（XSRF-TOKEN Cookie 级令牌，无页面绑定）+ m 站 SSR 详情兜底。robots.txt Disallow `/*?*`（官方反对抓搜索的立场）。
- **存活证据**：**[lastsunday/job-hunting](https://github.com/lastsunday/job-hunting)（425★，push 2026-08-31）——浏览器扩展注入 liepin 搜索页+详情页做增强，issue 区零猎聘封禁报告**（扩展形态的直接存在证明）；AgentMesh（CDP 只读采集）与 [Viy1204/liepin-cli](https://github.com/Viy1204/liepin-cli)（12★，2026-08-25，Puppeteer）均在维护；[loks666/get_jobs](https://github.com/loks666/get_jobs)（8.2k★）评价猎聘"打招呼无上限…较为推荐"。
- **结论**：推荐（条件）：需登录态；预留 safe.liepin.com 验证/登录弹窗的人工协作处理；只读用量 20 次/天远低于阈值。

## 四、拉勾 lagou.com — ⛔ 不接入（平台死亡，非技术原因）

- **平台已于 2026-05-21 自行申请破产**（北京拉勾网络技术有限公司；[21财经 2026-05-22](https://www.21jingji.com/article/20260522/herald/bfdfe1854470ed67cf26d61adb0946f0.html)：App 已下架、客服无人接听、官微 2025-03 停更）。
- 风控本身也强（今日实测阿里云 WAF 滑块前门；X-Anit-Forge-Token/X-Lagou-Token 页面环境依赖；搜索 30 次/15min 频控），但**关键事实是数据价值随平台死亡坍缩、站点随时可能下线**。
- 生态印证：2026 年活跃求职自动化项目（xixiluo95、AgentMesh、get_jobs）**全部不支持拉勾**；最后一个页面内嗅探扩展 NewJob（1041★）停更于 2024-06。

## 五、领英 linkedin.com — ⛔ 不接入（合规硬伤 ×3 + 大陆不可达）

- **合规**：①用户协议 §8.2.2 **逐字点名禁止"browser plugins and add-ons"抓取**（[UA 原文](https://www.linkedin.com/legal/user-agreement)）；②执法记录直接打击扩展形态——2023-01 Chrome 扩展 Browserflow 收停止侵权函（[HN 34583932](https://news.ycombinator.com/item?id=34583932)）、2025-01 诉 Proxycurl（2025-07 官宣胜诉解决）；③hiQ 案终局=合同违约成立，$50 万和解+永久禁令+删数据（"公开数据不违 CFAA"抗辩挡不住合同之诉）。
- **可达性**：linkedin.com 大陆封锁（Wikipedia 封禁名单；本机实测 HTTP 451）；大陆访问先天依赖违规国际信道（个人罚则上限 ¥15,000）。
- **数据价值**：InCareer 2023-08 关停（数据全删）+ **2025-03-03 起中国账单职位帖被强制关闭**（[官方帮助 a546396](https://www.linkedin.com/help/learning/answer/a546396?lang=zh-CN)）——"在领英找中国岗位"的价值已两轮清空。
- 技术上匿名职位端点（JobSpy 4k★ 在用）可用，但综合判定不接入。

---

## 对 M11 的回填建议

1. **policy 初始表**（`collection_policy.py` 内置）：`zhaopin: auto`、`shixiseng: auto`、`liepin: auto(需登录态)`、`zhipin: assist`（D30 红线）、`bilibili/zhihu: manual`（D30 红线）、`lagou/linkedin: blocked`（显式禁入，enqueue 直接拒绝并提示原因）。
2. **验收目标**：M11 §验收4 的 `pending-target` 解除——**auto 真机验收按 智联（首）+ 实习僧（次）执行**；猎聘带登录态作为第三目标。
3. **适配器工作量排序**：实习僧最简（SSR HTML+字体解码，无登录态）；智联次之（XHR 嗅探 fe-api，参考 xixiluo95 模式）；猎聘最重（登录态管理+safe 验证协作）。
4. **通用护栏增量**：三平台共用的"风控页识别关键词表"（智联：验证码|安全验证|操作频繁；猎聘：safe.liepin.com|登录）与冷却状态机，直接参考 xixiluo95 的工程实现（normal→cooldown_1h→cooldown_4h→blocked_today）。

## EXPAND（后续线索）

- LEAD: 实习僧移动端 API（iosapi.shixiseng.com）2026 现状未验——若仍开放，比字体解码更干净
- LEAD: 猎聘 safe.liepin.com 验证的触发频率——需 Playwright 会话实验量化
- LEAD: boss-agent-cli 同格式调研报告还有 zhipin.md/51job.md——未来扩平台可一次取齐
- DEAD END: 拉勾一切后续侦察——先确认站点存活再说
- DEAD END: 领英第三方职位搜索 API——产品不存在（官方 API 仅发帖方向）
