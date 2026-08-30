# M8–M10 追溯规格 — LLM 运行时配置 / 岗位胜任力建模 / 安全与分发

> ⚠️ 本文件是 **retroactive spec（事后追溯，实施先行）**：M8/M9/M10 实施于 D25 迁移前后，未按 SDD 纪律先行立 spec（文档链断裂的 P0-2 问题）。本文由 git 考古 + 当前 HEAD 代码现状反向补写，作为追溯性一页纸，不是实施前的裁决记录。后续里程碑恢复"先 spec 后实施"。
> 考证方法：`git log --oneline` + `git show --stat` + 代码核对；引用行号以当前 HEAD 为准。

## M8 — LLM 运行时配置（2026-08-22 → 08-24）

### 范围（做了什么）

- LLM fallback 切换 GLM-5.3（zhipuai coding-plan 端点）。
- 用户可配置 LLM API 设置（OpenBiliClaw 模式：运行时改 base_url/api_key/model，优先级 设置页 > env > 默认）。
- 设置 UI 先嵌在 sources 页，后独立为 #/llm 页。
- 同批修复：逐岗匹配并发信号量、空缓存短 TTL、LLM 空内容重试。

### 依据（commit + 代码位置）

| 内容 | commit | 代码位置 |
|---|---|---|
| GLM-5.3 fallback | cae1169 | talentforge/llm/client.py |
| LLM 设置存储 + API 端点 | 8995399 | talentforge/llm/settings.py、api/routes_llm.py |
| 设置 UI（嵌 sources 页） | 8995399 | web/js/views/sources.js |
| 设置独立 #/llm 页 | a7937c9 | web/js/views/llm.js、web/partials/llm.html |
| 并发/TTL/重试三修 | 25f9b31 | report/generate.py（信号量；并发度走 llm.settings.effective_match_concurrency，见 generate.py 模块 docstring） |

注：M8 各 commit 均无"M8"标签，里程碑边界按主题（LLM 运行时配置）划定；M9/M10 标签见各自 commit 文本，与此不同。

### 验收要点（现状如何验证）

- 单测：tests/test_llm_settings.py（8995399 引入）、tests/test_llm.py，全量 364 基线内全绿。
- 运行面：起服务 → #/llm 页改 base_url/model → 下一轮对话/匹配即时生效（settings 运行时读取）。
- 并发面：report/generate.py 信号量 + `effective_match_concurrency()`。

## M9 — 岗位胜任力建模（2026-08-26）

### 范围

TalentModel-skill 胜任力核心接入匹配链（commit 3cd4726，自带"M9"标签）：

- 岗位按 title 规则聚类分簇（RuleCompetencyClusterer）。
- 每簇建/复用 CompetencyModel（CompetencyModelCache 持久化，同类岗位复用维度框架）。
- matcher.match 注入 known_dimensions，输出 competency 逐维对齐（candidate_level）。
- 决策联动：胜任力维度大量缺失时下调 verdict（见下方技术债）。
- 工作台展示逐岗胜任力对齐（web/js/views/jobs.js）。

### 依据

commit 3cd4726；代码：talentforge/sources/job_competency.py（169 行）、domain/competency.py 扩展、matcher/coarse.py（known_dimensions 参数）、report/generate.py:85-112（编排）、web/js/views/jobs.js。

### 验收要点

- 单测：tests/test_job_competency.py（188 行，3cd4726 引入）。
- 端到端：跑一次决策报告 → items[].competency 逐岗维度对齐；同类岗位二跑命中簇缓存（generate.py:138-140 本批新建模型写回）。

### ⚠️ 已知技术债（如实记录，待收编）

决策调制"missing_dims ≥ 2 且均为 missing → apply 降 hold"写在 report/generate.py:113-117 编排层，绕过了 D15 锁定的 decision 核心——decision/verdict.py 的 decide() 不感知该规则，同一 Match 在核心与编排层可给出不同 verdict。已登记为待收编技术债；收编方向（规则下沉 decision/ 核心，或经 D15 可拓展外围协议显式注入）未裁，留待 decision 核心下次修订时处理。

## M10 — 安全加固 + 决策历史 + 分发（2026-08-26 → 08-29+）

### 范围

- **安全批次**（68e541f，"M10"）：凭据加密存储（talentforge/security/crypto.py，Fernet 对称加密 + 本机密钥文件）；扩展事件 origin guard（api/app.py，仅放行本机扩展来源）；移除 /api/debug 诊断端点——docs/research/m4-acceptance.md「D25 补充验收」曾注"诊断遥测保留"，该注已被 68e541f 取代。
- **决策历史 + 导出**（52a1c65，"M10 backtest foundation"）：decisions 历史表（storage/db.py）、报告端点写读历史、CLI `talentforge export`（cli.py，导出 decisions + jobs JSON，回测地基）。
- **首跑引导**（3272302，"M10 distribution"）：GET /api/onboarding/status（routes_onboarding.py）+ chat 页三步设置卡。
- **打包 spike**（0a9fd5e）：PyInstaller 单文件 exe 25.6MB、冷启动 1.0s（packaging/entry.py + talentforge.spec）。
- **分发加固系列**：4e098c2（Windows 构建 + Inno Setup 安装器）、01fa05f/e828f29（安装器修复）、2b8b898（单实例 exe + origin guard 下解锁扩展事件）、3814f19（扩展 CI 打包）、8980703（Node 24）、31fbbad（macOS dmg + Linux tar.gz 三平台矩阵）、1bb4287（pyinstaller spec 自含 + CI 冒烟运行产物 exe）、d047074（Firefox 构建目标，`npm run build:firefox` → dist-firefox/，extension/FIREFOX.md）。

### 依据

commit 68e541f / 52a1c65 / 3272302 / 0a9fd5e + 分发系列；代码：talentforge/security/crypto.py、storage/db.py（decisions 表 :43、insert_decision/list_decisions）、api/routes_onboarding.py、packaging/entry.py + installer.iss、.github/workflows/build.yml、extension/FIREFOX.md。

### 验收要点

- 单测：tests/test_security.py（111 行）、tests/test_decisions_store.py（73 行）、tests/test_onboarding.py（55 行）。
- 打包：CI 三平台产物 + exe 冒烟运行（1bb4287）；`npm run build:firefox` 出 dist-firefox/。
- 运行面：首跑打开首页 → 三步引导卡（/api/onboarding/status 驱动）；`talentforge export --out x.json` 出决策历史。

## 与决策链的关系（缺环说明）

- M8/M9/M10 均无 D 编号决策、无先行 spec——D25 迁移期文档链断裂的一部分（design-decisions.md 状态机已同批修复，追溯索引见该文件末表）。
- M9 决策调制与 D15 的冲突见 M9 技术债；M10 移除 debug 端点与 m4-acceptance.md 旧注的取代关系已在 M10 范围内注明。
