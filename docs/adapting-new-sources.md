# 适配新平台源指南（D25 架构：服务器零浏览器采集）

> 本文档回答「怎么给 TalentForge 加一个新数据源」。核心原则来自 D25 决策：
> **反爬强的站一律走浏览器扩展（用户真实登录态内采集），服务器不碰浏览器。**
> 后端在 exe 分发版本中已移除 playwright/Chromium（体积 200MB+），这条约束是硬性的。

## 先决断：新源走哪条路？

| 新源特征 | 走哪条路 | 示例 |
|---|---|---|
| 反爬强、需要真实登录态（cookie/stoken） | **扩展采集**（kind: extension） | Boss / B站 / 知乎 |
| 有公开 API、无需登录或可接受匿名限流 | **公开 API**（kind: public） | GitHub / Gitee / arXiv |
| 无公开 API 且反爬弱 | 公开 API 路线的特例：HTTP 抓取 + 解析（无需浏览器） | — |

**M11 补充（D30 分级采集）**：岗位类平台加入扩展前先过 `sources/collection_policy.py` 分档（auto/assist/manual/blocked，参考 `docs/research/m11-platform-recon.md` 侦察方法与 `docs/spec-m11-graded-collection.md`）；auto 档经任务子系统无人访问，适配器参考 `extension/src/shared/platforms/shixiseng.ts`（SSR 直采）与 `zhaopin.ts`（MAIN-world hook 截获 XHR）两种范式，并在 `manifest.json` 注册 content script（必要时加 `world: "MAIN"` 入口）与 `scripts/build-extension.mjs` 构建清单。

**判定铁律：**
- 服务器绑定 `127.0.0.1`，**绝不**为采集起 Chromium/Playwright（D25：服务器 IP 会被风控，扫码登录会被投毒）
- 需要用户登录态的站 → 必须走扩展（用户浏览器里 cookie 天然有效）
- 匿名能拿到的数据 → 走公开 API，落 `work_sources.py` 同构的采集器

## 路线 A：扩展采集（反爬强站）

新增一个平台分三步，全部在 `extension/` 内，vitest 覆盖：

1. **共享适配器** `extension/src/shared/platforms/<site>.ts`
   - 实现 `mapXxxJob(item) -> 归一化卡片`（对照 `boss.ts`：字段映射、截断、URL 构造）
   - 实现 `collectVisibleJobs(root)`（DOM 兜底，对照 `boss.ts` 的 selectors 模式）
2. **content script** `extension/src/content/<site>.ts`
   - 对照 `kernel.ts`（B站/知乎用 kernel 事件上报；Boss 用主动采集 POST `/api/jobs/batch`）
   - 新站如果同 B站/知乎（浏览行为 → 事件）→ 复用 kernel，只加选择器
   - 新站如果同 Boss（搜索页列表 → 岗位批量入库）→ 走 `collectVisibleJobs` + batch 上报
3. **manifest 注册**：`content_scripts` + 必要时 `host_permissions`
   - 测试：`extension/src/__tests__/<site>.test.ts`（对照 `boss.test.ts`）

## 路线 B：公开 API（GitHub/Gitee/arXiv）

新增一个平台在 `talentforge/sources/` 内，pytest 覆盖：

1. **采集器** `talentforge/sources/<site>_source.py`
   - 对照 `work_sources.py`：`async def fetch_xxx(...) -> list[WorkArtifact]` 或同类
   - 必须带**限流友好**（对照 GitHub 60/h 未认证教训：失败结果不写长缓存，短 TTL）
   - 必须带**软降级**（对照 504 教训：单仓库失败不毁整批）
2. **分级规则**：进 `work_grading.py` 或独立分级器（对照 R1/R3/R9 信号规则）
3. **API 接线**：`routes_work.py` 的 fetch body 加字段（对照 WorkFetchRequest 契约）
4. **前端卡**：`routes_sources.py` 静态卡加条目 + `sources.js` 的 WORK_KEYS 加 key
   - 测试：对照 `test_work_sources.py` / `test_work_grading.py`（MockTransport 注入，不打真实网络）

## 测试覆盖对照（删 scraper 后依然全绿）

| 层 | 测试文件 | 覆盖 |
|---|---|---|
| 扩展适配 | `extension` vitest（45 个） | boss.ts 映射/采集/URL、kernel 事件 |
| 公开 API | `test_work_sources.py` / `test_work_grading.py` | GitHub/Gitee/arXiv 采集与分级 |
| 决策链路 | `test_report.py` / `test_api_*.py` | generate_report 消费库内岗位（与采集解耦） |

## 为什么可以放心删 scraper

- `boss_scraper.py` 走的是「服务器起 Chromium 抓 Boss」——D25 实测：服务器 IP 被风控（code 35）、QR 登录被投毒、disable-devtool 关 tab，这条路**已被证伪**，不是"没测试了"而是"路没了"
- Boss 现在由扩展采集（用户浏览器内 wapi + DOM 双通道），真实岗位已入库 156+ 条实证
- 适配新源的两条路（扩展 / 公开 API）测试都在，指南就在本文档
