# M5 规格 — 作品源（GitHub/Gitee/arXiv）+ 简历产出伴随

> 状态：待用户复核。上游：D23（作品源三层防线）、D24（信号理论分级规则）、D25（公开 API 走服务器直连）、`docs/research/easycv-teardown.md`（简历产出借鉴）。
> 连通性实测（2026-08-23）：GitHub API ✅（未认证 60/h，token 可升 5000/h）；arXiv API ✅（XML 全开放）；Gitee API ⚠️（按名取仓/用户仓库正常，搜索无 token 返回空——作品源场景不依赖搜索）。

## 0. 定位

作品源 = **稀疏高价值信号**（D23）：本科 4 年可能就 1 篇论文 + 几个 repo，无重复可累积，价值在**判别**而非计数。与浏览信号（trial 攒证据）相对——作品证据**公开可验证，直通 verified**（D20 两半中的 verified 半）。

## 1. 数据模型

### 1.1 WorkArtifact（新域模型）

```python
class WorkArtifact(BaseModel):
    artifact_id: str            # "{platform}:{repo_full_name|paper_arxiv_id}"
    platform: Literal["github", "gitee", "arxiv"]
    kind: Literal["repo", "paper"]
    title: str                  # repo 名 / 论文标题
    url: str
    # 结构化事实层（LLM 不参与判断，D23 防线 a）
    facts: dict[str, Any]       # repo: 语言分布/stars/forks/commits/持续月数/is_fork/pushed_at；paper: venue/作者排序/年份/摘要
    # 规则分级层（查表判定，D23 防线 b）
    grade: str                  # "strong" | "normal" | "weak"（见 §2 规则表）
    grade_reasons: list[str]    # 命中的规则条目（可解释）
    fetched_at: datetime
```

### 1.2 持久化

`data/artifacts.json`（append/merge by artifact_id；env `TALENTFORGE_ARTIFACTS_PATH` 可覆盖）——与 feedback_log 同风格，简单 JSON 即可（个人工具量级 <100 条）。

### 1.3 与画像的接法

- 作品主张 = **verified 直通**（D23④）：`NarrativeClaim(state="verified"` —— 等等，state 是 trial/active/archived 三态（D20 保持 additive）。落法：作品主张走 `state="active"` + `sources[0]={kind:"work", ref:artifact_id}` + evidence_count 初始 1，grade 进 confidence 映射（strong=0.9/normal=0.7/weak=0.5）。**不新增 state 值**（契约红线：Literal 不动）。
- 用户校对兜底（D23 防线 c）：画像页待定池上方加"作品主张"卡片区（读 work 域），可驳回（驳回 = 该 artifact 不再生成主张，存 dismissed 列表）。

## 2. 分级规则表（D24 信号理论：高成本低造假 = 强信号）

| 规则 | 判定 | 信号逻辑 |
|---|---|---|
| R1 is_fork=true | grade ≤ weak（fork 直接降权，D23 原文） | fork 无原创成本 |
| R2 commits < 10 | weak（课程作业概率大） | 信号成本趋同（credential inflation 教训） |
| R3 持续 commit ≥ 6 个月 | strong 证据 | 长期投入难伪造 |
| R4 一作（authors[0]）+ venue ∈ CCF-A/B 白名单 | strong | 顶会一作 = 高成本低造假 |
| R5 venue ∈ CCF-C 或非顶会一作 | normal | 可信但有更优信号 |
| R6 非一作顶会 | normal | 参与度信号 |
| R7 stars | **仅参考不进 grade**（D23 原文） | stars 可刷，信号弱 |
| R8 语言分布主语言占比 > 80% 且 repo 数 ≥ 3 同语言 | normal | 技术栈一致性佐证 |

- CCF 白名单：内置精简表（A/B 类会议/期刊名列表，~50 条常用项，覆盖 AI/系统/软工；不是全集，查不到 = 非顶会处理，宁缺勿滥）
- 规则按序短路：weak 规则（R1/R2）先判，命中即定；否则 strong 条件（R3/R4）；缺省 normal/weak 由 R5-R8 收敛
- 每条 grade_reasons 记录命中规则号 + 一句话解释

## 3. 采集器（sources/work_sources.py）

```python
class GitHubSource:     # 用户名 → repos + languages + commits 概要
    async def fetch_user_works(username: str) -> list[WorkArtifact]
class GiteeSource:      # 同上（gitee API v5）
class ArxivSource:      # 作者姓+名 → 论文列表（标题/摘要/作者/日期；venue arXiv 本身=preprint，grade 上限 normal，除非标题含会议名再查 CCF）
```

- GitHub：`/users/{u}/repos`（排除 fork 可选）→ 每 repo `/repos/{full}/languages` + commits 计数（`?per_page=1` 读 Link header 总数）；限流遇 403 → 提示配 token（env `TALENTFORGE_GITHUB_TOKEN`）
- Gitee：`/users/{u}/repos` + repo 详情自带 stargazers/forks/pushed_at；语言取 repo.language
- arXiv：`export.arxiv.org/api/query?search_query=au:"{last} {first}"` XML → feedparser 或标准库 xml 解析
- 超时/失败优雅降级（单源失败不影响其他源）
- **LLM 零参与**（防线 a：拉取只提结构化事实）

## 4. API 面

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/work/artifacts` | GET | 全部作品（facts+grade+reasons，校对卡片用） |
| `/api/work/fetch` | POST | body {github_user?, gitee_user?, arxiv_author?} → 拉取+分级+存库，返回新增/更新数 |
| `/api/work/claims` | POST | 把 artifacts 生成 verified 主张写入画像（body {artifact_ids?, all?: bool}；驳回过的跳过） |
| `/api/work/dismiss` | POST | body {artifact_id} → 驳回（不再生成主张） |

## 5. Web 落点

- 平台源页：GitHub/Gitee 卡升级为可配置（用户名/作者名输入框 + "拉取作品"按钮 + token 选填）——复用 sources 卡交互模式
- 画像页：新增"作品主张"区块（待定池上方）：grade 徽章（strong=terracotta/normal=琥珀/weak=stone）+ facts 摘要 + grade_reasons + "入画像/驳回"按钮
- 工作台 gap/补短板：后续版本接 D24 信号组合优化（本里程碑不做）

## 6. 简历产出伴随（easyCV 借鉴，最小版）

- `GET /resume` 静态页：profile + verified 作品主张 → Jinja2 A4 模板 → 打印导出 PDF（window.print + print CSS，零依赖）
- 模板套 DESIGN.md 暖纸面体系（不抄 easyCV 蓝色主题）
- 产出内容：basics（画像 narrative/技能）+ education + projects（作品 artifacts：repo/论文 + grade 信号）——数据从 profile + artifacts 读

## 7. 范围外

- Gitee 搜索（无 token 不可用）；GitHub commit 明细分析（只取计数与时间跨度）；简历多模板；作品自动发现（需用户给 ID）

## 8. 验收口径

1. 单元：分级规则表逐条测试（R1-R8 + CCF 查表 + 短路顺序）；三源解析器（fixture XML/JSON）
2. API：fetch/artifacts/claims/dismiss 契约 + 限流降级（mock transport）
3. Web：作品卡渲染 + 驳回交互（node:test）
4. 端到端：真机拉取你的 GitHub 用户名 → artifacts 入库 → claims 写画像 → 画像页作品区可见 → `/resume` 出 A4 页可打印
