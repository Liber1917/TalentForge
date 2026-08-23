# M6 规格 — 信号投资循环（gap → 项目推荐 → 参与回流）

> 状态：待用户复核。上游：D26（GitHub 双用途定调：作品信号 + 信号投资循环）、D24（补短板建议本质是信号组合优化）、D23（三层防线）。
> 现状缺口：matcher/generate 不产出 gap/remediation（common.py 留空数组占位）；工作台详情 gap 区块空转；GitHub search API 未用于推荐。

## 0. 定位与循环

D26 的信号投资循环具体化：

```
决策/匹配发现 gap（如"缺 K8s 实践"）
  → 推荐：GitHub search 按_gap 关键词搜优质 repo（本里程碑）
  → 用户参与（fork/PR/commit——线下行为）
  → 回流：M5 作品源下轮拉取捕获新强信号（已就绪）
  → gap 消失，下一 gap 浮现
```

本里程碑交付**发现与推荐**两环（参与回流已由 M5 覆盖）。

## 1. Gap 产出（matcher 扩展）

### 1.1 CoarseMatcher prompt 扩展（gap 提取）

`COARSE_MATCH_SYSTEM_PROMPT` 输出 schema 增加 `gaps` 字段（不破坏现有字段）：

```json
"gaps": [{"skill": "Kubernetes", "severity": "major|minor", "evidence": "JD 要求 K8s 部署经验，画像无容器编排记录"}]
```

- 最多 3 条，按 severity 排序；evidence 必须引用 JD 与画像的落差（D23 防线 a：结构化事实）
- 兼容：LLM 未输出 gaps → 空列表（旧响应不炸）

### 1.2 决策缓存扩展

`generate_report` items / decisions 缓存增加 `gaps`（随 verdict/reason 一起存）；`GET /api/jobs` 的 job_contract 把 gaps 透传到工作台（替换现在的空数组）。

## 2. 项目推荐（gap → GitHub 优质 repo）

### 2.1 采集器（sources/project_suggest.py 新建）

- `async def suggest_projects(gap_skill: str, limit: int = 5) -> list[dict]`：
  - GitHub search：`GET /search/repositories?q={gap}+language:{画像主语言}?}&sort=stars&order=desc&per_page=10`
  - **规则筛（D23 防线 b，LLM 不参与）**：
    - R-s1 stars < 100 剔除（冷门）或 stars > 50000 降为"参考"（太成熟，新人 PR 难合并）
    - R-s2 `pushed_at` 30 天内（活跃）
    - R-s3 open_issues < 500（维护得动）
    - R-s4 description 非空且与 gap 语义相关（关键词包含）
    - R-s5 fork 仓库剔除（参与上游）
  - 每条返回：{full_name, url, stars, description, language, pushed_at, good_first_issues(可选: search issues label="good first issue" 数量), why(命中规则的人话)}
- 限流：search API 未认证 10 req/min（token 30）——缓存结果到 data/suggestions.json（TTL 24h，key=gap_skill）

### 2.2 API（routes_work.py 扩展或新 routes_suggest.py）

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/suggest` | POST | body {gap_skill} → 推荐列表（走缓存） |
| `/api/suggest/for-job` | POST | body {job_url} → 读该 job 的 gaps → 逐 gap 推荐 |

### 2.3 Web（工作台详情面板）

- gap 区块激活（现有空区块）：每条 gap 显示 skill + severity + evidence
- gap 旁"补信号"按钮 → 展开 3-5 个推荐 repo 卡（stars/desc/why/链接 + "good first issue" 计数）→ 外链新 tab
- fixtures 模式：LOCAL_SUGGEST_FIXTURES 示例

## 3. 范围外

- PR/commit 自动追踪（参与回流走 M5 作品源自然周期）；推荐个性化排序（v1 规则筛够用）；Gitee 推荐（搜索无 token 不可用）

## 4. 验收口径

1. 单元：prompt gaps 解析（含旧响应兼容）/ 推荐规则筛逐条 / 缓存 TTL
2. API：suggest 契约 + for-job 联动（job 无 gaps → 空）
3. Web：gap 区块 + 推荐卡渲染（node:test）
4. 真机：库内真实岗位跑决策 → gap 出现 → for-job 推荐 3-5 条真实 repo
