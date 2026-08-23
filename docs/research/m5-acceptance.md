# M5 验收笔记 — 作品源（GitHub/Gitee/arXiv）+ 简历产出

> 验收依据：`docs/spec-m5-work-sources.md` §8（验收口径）；`docs/plan-m4.md` 传承。
> 验收日期：2026-08-23。执行人：agentic worker（T5）。
> 结论速览：**四层验收全过（§1–§4）；真机拉取 torvalds 12 仓库全链路验证（分级正确、入画像、简历页渲染）；发现并修复真实缺陷一处（GitHub commits 接口间歇 504 → 仓库级软降级）。用户本人 GitHub/arXiv 拉取标记 pending-user。**

---

## 1. 单元测试（分级规则 + 三源解析）

`tests/test_work_sources.py` 23 项全绿：R1 fork→weak 短路 / R2 commits<10→weak / R3 持续≥6月→strong / R4 一作+CCF→strong / R5 非顶会一作→normal / R6 二作顶会→normal / arXiv 无 venue→normal 封顶 / R7 stars 只进 reasons / R8 主语言占比 reason / CCF 大小写不敏感；GitHub（Link header commits 计数）/Gitee/arXiv（Atom XML）解析器；WorkStore merge/dismiss/容错。全部 MockTransport 注入不真联网。

## 2. API 测试（9 项）

`tests/test_api_work.py`：fetch 三源并发 + 单源 WorkSourceError 降级 warnings / 空参零操作 / refetch added=0；artifacts + dismissed 幂等；claims 全量写入（grade→confidence 0.9/0.7/0.5、state=active、kind="work"）+ 同文本二写 skipped + 驳回排除 + 画像缺失兜底。

## 3. Web 测试（15 项新增，89 全绿）

sources：作品拉取展开区（github/gitee 用户名、arxiv 作者名）/ grade 中文映射 / XSS；profile：作品卡渲染（facts 摘要 + grade 徽章映射 active/trial/archived）/ 已入画像态 / 驳回移除 / work-section 骨架。

## 4. 简历页测试 + 真机验收（核心）

### 真机链路（torvalds，2026-08-23）

| 步骤 | 结果 |
|---|---|
| POST /api/work/fetch {github_user: "torvalds"} | ✅ 12 仓库入库（含 commits/languages/首末时间），零警告 |
| 信号分级 | ✅ 规则在真实数据上正确运作（见下表） |
| POST /api/work/claims {all: true} | ✅ written: 12, skipped: 0 |
| 浏览器 GET /cv | ✅ A4 纸面（793.7px）、12 作品 strong 排序在前、打印按钮、facts 摘要 |
| 浏览器 #/profile 作品区 | ✅ 12 张作品卡渲染 + 18 张主张卡共存 |

### 分级规则真机抽验（torvalds 数据）

| 仓库 | facts | grade | 命中规则 |
|---|---|---|---|
| linux | 1,477,103 commits / 7798 天 / 非fork | **strong** | R3 持续≥6月 |
| uemacs | 245 commits / 7737 天 | **strong** | R3 |
| libgit2 | 14,688 commits 但 **fork=True** | **weak** | R1 短路（fork 无原创成本，commits 高也不救） |
| HunspellColorize | 5 commits | **weak** | R2 课程作业概率 |
| AudioNoise | 47 commits / 120 天 | normal | 缺省收敛 |
| （全部） | stars 398–243,878 | 不影响 grade | R7 仅记 reason |

**D24 信号理论的落地实证**：linux 的 24 万 stars 不加分（可刷），fork 的 1.4 万 commits 直接降权（无原创成本）——高成本低造假的信号（持续 commit 的原创仓库）才是强信号。

### 发现并修复的真实缺陷

- **现象**：真机首次拉取 `total_fetched: 0, warnings: ["github: HTTP 504 …/commits"]`——单个仓库的 commits 接口偶发 504 毁掉整批。
- **修复**（0d11594）：`_commit_summary` 单仓库详情 5xx 软降级为 (0, "", "") 不阻断整批（与 `_languages` 容错对齐）；限流 403/429 仍按源级错误上抛。repos 列表自带 stars/forks/language，缺 commits 只让分级保守化。
- **回归**：23 单测全绿；修复后真机重拉 12/12 成功零警告。

## 5. 限制说明

| 限制 | 说明 |
|---|---|
| GitHub 未认证限流 60 req/h | 每仓库 3 次详情请求，约 15-18 仓库/小时；env `TALENTFORGE_GITHUB_TOKEN` 升 5000/h |
| Gitee 搜索无 token 返回空 | 作品拉取（users/{u}/repos）不受影响；spec §7 范围外 |
| arXiv preprint 无 venue | grade 上限 normal，标题含会议名查 CCF 才可能 strong |
| commits 5xx 软降级 | 该仓库 span_days=0、commits=0 → 分级保守化（宁弱勿滥） |
| 论文一作判定按名字精确匹配 | arXiv 名字变体（Zhang San/San Zhang）可能漏判一作 → 落 normal（保守正确） |
| Gitee/GitHub 公司字段 | 列表接口无公司概念，facts 无 company（作品是个人仓库） |

## 6. 全量测试基线

- Python pytest：**218 passed**（T1 +23、T2 +9、T4 +4，原 182 无回归）
- Web node:test：**89 passed**（T3 +15，原 74 无回归）
- Extension vitest：**45 passed**（M4 期间 +3，无回归）

## 7. pending-user

- 拉取**用户本人**的 GitHub/Gitee/arXiv（平台源页输入用户名或告知我代跑）→ 个人作品主张 + 个人简历产出。

---

## M6 验收附录 — 信号投资循环（2026-08-23）

> 依据：D26 + spec-m6-signal-investment.md。四任务链：T1 gap 产出（b12f66d）→ T2 推荐器（d81f7d2）→ T3 工作台 UI（01da196）→ T4 真机验收（本节）。

### 真机链路（用户真实数据）

| 环节 | 结果 |
|---|---|
| 决策管线产 gap（report/run 3 岗） | ✅ go 岗 → "Golang (major)"、量化岗 → "量化金融领域经验 (major)"，evidence 引用 JD×画像落差 |
| gap → GitHub 推荐（/api/suggest） | ✅ 规则筛后 5 条（awesome-go/caddy 等，全"超大项目参考"标记——top 结果均为 >50k stars 属实） |
| for-job 联动 | ✅ 读 decisions 缓存 gaps → 逐 gap 推荐分组 |
| 浏览器 UI | ✅ 详情 gap 条目（skill+severity 徽章+evidence）→ 补信号 → 5 张推荐卡（stars/desc/why/参与外链） |

### 排查实录（T4）

1. **决策路由超时**：对话页决策触发对 156 个库内岗位逐个 LLM 匹配（分钟级）——验收改用 report/run limit=3；生产侧全量决策耗时问题记入 backlog（需批量并发/缓存）。
2. **GitHub search 未认证限流**：search API 未认证 10 次/分，首次 for-job 全空（403 被容错为空列表）且**空结果被缓存 24h**——教训：失败结果不该长缓存（记 backlog：失败不缓存/短 TTL）。token 环境变量生效后正常。

### 限制（backlog）

- 决策全量耗时（需并发或按需匹配）
- 推荐缓存：失败空结果也缓存 24h（应只缓存成功结果）
- 语言不在缓存键（T2 deviation 记录）
- 参与回流检测依赖 M5 作品源手动重拉（无自动周期）

### 全量基线

pytest **287** + web node:test **100** + extension vitest 45 全绿。
