# TalentForge
人才锻造台

## M2a 岗位决策报告

端到端抓取 Boss 直聘岗位 → 归一化 → 场域风险标记 → 粗匹配 → 三元决策，输出 JSON 报告。

### 安装

```bash
pip install -e .
playwright install chromium   # 首次需下载浏览器内核
```

### 登录 / 配置 cookie

真实抓取需要 Boss 直聘登录 cookie，二选一（env 优先）：

1. **env 原始串**：设置环境变量 `TALENTFORGE_BOSS_COOKIE` 为浏览器里复制出的 cookie 串（`wt2=xxx; wbg=yyy; ...`）：
   ```bash
   export TALENTFORGE_BOSS_COOKIE="wt2=...; wbg=..."
   ```
2. **jobclaw 登录文件**：用 jobclaw 登录 Boss 后产物位于 `~/.jobclaw/cookies/boss.json`（`{"saved_at": ..., "cookies": [...]}` 格式），TalentForge 自动读取。

未配置 cookie 时抓取会报 `BossCookieNotFoundError` 并提示配置方式。

### 跑报告

```bash
# 真实验收命令（需 cookie，见上）
talentforge report --profile docs/demo/profile.json --query 后端工程师 --city 深圳 --limit 20

# 演示 / 无 cookie 模式：直接喂本地 HTML，跳过浏览器
talentforge report --profile docs/demo/profile.json --query 后端工程师 --city 深圳 \
  --offline-file talentforge/sources/fixtures/boss_search_page.html --db /tmp/tf.db
```

- `--offline-file`：跳过 Playwright 抓取，直接把本地搜索页 HTML 作为输入，适合无登录演示与测试。
- `--db <path>`：指定 SQLite 落库路径（默认 `data/talentforge.db`），岗位按 `job_url` 去重。
- 真实抓取默认单次 ≤3 页、页间随机延迟 5-10s；命中验证码时按合规红线暂停并报错，需人工介入（不绕过）。

### 输出字段

报告为 JSON，`summary` 给出计数，`items` 逐岗列出：

| 字段 | 含义 |
|---|---|
| `summary.n_jobs / n_apply / n_hold / n_skip` | 评估岗位总数 / 建议投递 / 暂缓 / 建议跳过 |
| `items[].verdict` | 三元决策：`apply` / `hold` / `skip` |
| `items[].reason` | 决策理由（粗匹配的推理摘要） |
| `items[].risk_hits` | 命中的结构性风险标签清单（如 `996 工作制`），空为未命中 |
| `items[].reflective_question` | 一句反思性反问（基于风险命中或缺失维度，M3 换 LLM 生成） |

---

## M2b 插件内容采集（B站+知乎）

浏览 B站/知乎 → Chrome 插件只读采集点击/搜索/滚动 → 事件入库（event_id 幂等）→ α 待定池 trial 主张累积，验证"画像自长"链路。

### 插件开发 / 构建

```bash
cd extension
npm install            # 首次（可用 npmmirror 镜像加速）
npm run typecheck      # TS strict 检查
npm run build          # 产出 extension/dist/（background + content js）
npm run test           # vitest 单测（kernel/buffer/adapter/endpoint）
```

`extension/manifest.json`：MV3，content_scripts 覆盖 `*.bilibili.com/*` 与 `*.zhihu.com/*`，`host_permissions` 含 `http://127.0.0.1/*`（flush 目标）。

### 后端起服务

```bash
# 终端 1：启动事件接收 server（默认 127.0.0.1:8420，POST /api/events）
nohup .venv/bin/python -c "from talentforge.api.events import events_server; from talentforge.storage.db import init_db; s = events_server(conn=init_db('data/talentforge.db', check_same_thread=False)); s.serve_forever()" &
```

> 注意：调用方自建 conn 必须带 `check_same_thread=False`（HTTP server 多线程使用）；`events_server()` 不传 conn 时内部已处理。

### 插件安装 / 加载

1. `cd extension && npm run build`
2. Chrome 打开 `chrome://extensions` → 开启"开发者模式" → "加载已解压的扩展程序" → 选 `extension/` 目录
3. 浏览 https://www.bilibili.com/ 或 https://www.zhihu.com/，点击卡片 / 搜索
4. 事件自动 POST 到 `http://127.0.0.1:8420/api/events`（30s 内 flush），核验：

```bash
sqlite3 data/talentforge.db "SELECT event_id, event_type, url, source_platform, received_at FROM events ORDER BY received_at DESC LIMIT 20;"
```

### 离线演示（无需浏览器 / 无需插件）

```bash
# 1) 造几条浏览事件 JSONL（每行一个事件），入库
.venv/bin/talentforge events-ingest events.jsonl --db /tmp/m2b-demo.db

# 2) 从事件表消费最近事件，推断 trial 主张并写回画像文件
.venv/bin/talentforge profile-update --profile docs/demo/profile.json --limit 5 --db /tmp/m2b-demo.db
```

`profile-update` 后，`docs/demo/profile.json` 的 `narrative_claims` 会新增 `state="trial"` 的主张，每条 `sources[0]={kind:"behavior", ref:<event_id>}`——即"画像自长"证据。

### 真实验收步骤

详见 `docs/research/m2b-acceptance.md`：后端契约 curl 验收（§1）、插件↔后端浏览器端到端（§2，pending-user）、画像自长链路（§3）。

---

## M3 Web 界面（对话 / 工作台 / 画像）

FastAPI 统一承载 API + 静态 Web，三视图 SPA（纯 vanilla JS + hash 路由）：`#/chat` 对话首页 / `#/jobs` 决策工作台 / `#/profile` 画像面板。

### 启动

```bash
python -m uvicorn talentforge.api.app:create_app --factory --port 8420
```

浏览器打开 http://127.0.0.1:8420/ 。静态资源与 API 同一端口（/api/events 插件采集端点保留，与 M2b 共存）。

### 数据源切换

- **默认离线 fixtures**：开箱即用，三视图用本地镜像假数据渲染（5 轮对话 + 4 类卡片、8 岗位三态、画像四 tab），无需 LLM / 无需数据库。
- **真后端联调**：URL 加 `?real=1`（或 localStorage 置 `tf_real=1`）→ 命中 FastAPI 真端点（真实 LLM、读写 SQLite 与画像文件）。

### 三视图

| 视图 | 路由 | 做什么 |
|---|---|---|
| 对话首页 | `#/chat` | 陪伴入口：聊天 + 内嵌卡片（DecisionCard / ClaimCard / RiskNote / ReflectivePrompt）。发"帮我看看深圳后端岗"触发决策；聊自己沉淀 trial 主张；反思回答写回画像 |
| 决策工作台 | `#/jobs` | 工具面：岗位三态列表（VerdictBadge）+ 筛选（搜索/城市/verdict）+ 详情面板（理由链/风险/gap 补短板）+ 生成报告（异步跑 M2a 管线） |
| 画像面板 | `#/profile` | 读/校对面：待定池主张确认/驳回 + 叙事/效用/结构位置三轨 + 八格网格 + 简历校对 + 导出 JSON |

Primitive Showcase（设计原语三断点验证）：http://127.0.0.1:8420/showcase.html

### 测试

```bash
# Python 后端（app 工厂 / fixtures / 真实路由 / 全量组件）
.venv/bin/pytest

# Web 前端渲染断言（node:test + vm，无第三方依赖）
node --test web/tests/chat.test.mjs web/tests/jobs.test.mjs web/tests/profile.test.mjs
```

### 真实验收步骤

详见 `docs/research/m3-acceptance.md`：离线假数据演示（§1）、真后端联调数据流（§2）、验证证据（§3）、限制与 pending-user 清单（§4）。

---

## M4 反馈闭环（显示性偏好回流）

记录你的真实求职行为 → 偏好序自动微调 → 画像越用越准（D15 稳定核心补齐）。

### 使用

1. 工作台（`#/jobs`）选岗位 → 详情底部"我的行动"：
   - **我已投递 / 我跳过了**：一键记录决策（你的真实行为，覆盖系统建议）
   - **记录结果**：展开 面试中/已拒/offer/无回音
2. 画像页（`#/profile`）效用轨查看回流效果：`薪资 30-40万›40万以上…（含 N 次决策回流）`
   - **apply + offer/interview → 该薪资段位自动升 1 位**；其他行为记入 evidence 注释
3. 数据落 `data/feedback_log.json`（幂等：同岗位同动作更新不重复），偏好写回画像文件

### API

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/feedback/events` | POST | 记录决策/结果，驱动偏好回流 + 叙事修正 |
| `/api/feedback/events?limit=50` | GET | 最近回流条目（倒序） |
| `/api/feedback/summary` | GET | 决策分布统计 |

规则版无 LLM 参与偏好（D18 人机边界）；详见 `docs/research/m4-acceptance.md`。

---

## M5 作品源 + 简历产出（GitHub/Gitee/arXiv）

拉取你的公开作品 → 信号分级（D24：持续 commit 的原创仓库/顶会一作 = 强信号）→ verified 主张入画像 → A4 简历产出（D23 三层防线：LLM 零参与判断）。

### 使用

1. 平台源页（`#/sources`）→ 展开 GitHub/Gitee 卡输入用户名（或 arXiv 卡输入作者名）→ **拉取作品**
2. 画像页（`#/profile`）顶部"作品主张"区：查看 grade 徽章（强/普通/弱）+ 结构化事实 + 分级依据 → **入画像** / **驳回**
3. 简历产出：`http://127.0.0.1:8420/resume` → 打印/导出 PDF（A4 排版，作品按信号强度排序）

### API

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/work/fetch` | POST | 拉取 `{github_user, gitee_user, arxiv_author}`（任选）并入库 |
| `/api/work/artifacts` | GET | 作品列表 + 驳回清单 |
| `/api/work/claims` | POST | 作品 → verified 主张写入画像（`{artifact_ids}` 或 `{all: true}`） |
| `/api/work/dismiss` | POST | 驳回作品（不再生成主张） |

GitHub 未认证限流 60 请求/时（每仓库 3 次详情）；`TALENTFORGE_GITHUB_TOKEN` 可升至 5000/时。详见 `docs/research/m5-acceptance.md`。
