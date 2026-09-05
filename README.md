# TalentForge
人才锻造台

本地求职决策助手：画像 → 岗位采集 → 匹配 → 三元决策 → 反馈回流，全数据留在本机。

- 北极星：锻造人才，非迎合市场（`docs/design-decisions.md` D10）
- 采集架构（D25）：反爬平台一律走**用户真实浏览器页面内采集**（浏览器扩展），服务器侧抓取已移除——零对抗、零封号面
- 设计决策与各里程碑 spec 见 `docs/`（SDD 开发，决策 → spec → 实现全链可追溯）

## 安装

```bash
pip install -e .
```

或直接用分发包（CI 产物）：Windows `TalentForgeSetup.exe`（Inno Setup 安装器）/ macOS `TalentForge-macOS.dmg` / Linux `talentforge-linux.tar.gz`。exe 双击即起服务并自动打开浏览器，零命令行。

## 数据从哪来：浏览器扩展采集（D25 唯一通道 + D30 分级采集）

扩展是 Boss 岗位与 B站/知乎浏览行为的**唯一采集通道**（D25）；M11 起按平台风控分级（D30）：

| 平台 | 模式 | 说明 |
|---|---|---|
| Boss zhipin | assist | 搜索页"辅助浏览"开关：拟人滚动脉冲加载更多，人在场启停 |
| 智联 zhaopin | auto | 任务派发无人访问；MAIN-world hook 截获 fe-api 岗位 JSON |
| 实习僧 shixiseng | auto | 任务派发无人访问；SSR 卡片直采（数字字段有字体混淆局限） |
| B站/知乎 | manual（红线） | 行为语义平台，自动访问=伪造显示性行为（D6/O1） |
| 拉勾/领英 | blocked（禁入） | 平台破产 / 合规硬伤（docs/research/m11-platform-recon.md） |

任务端点：`POST /api/tasks/visit`（仅 auto 平台，冷却/配额护栏）→ `GET /api/tasks/next`（扩展 alarm 轮询领取）→ `POST /api/tasks/{id}/report`；策略覆盖 `data/collection_policy.json`（`paused:true` 全局停）。

```bash
cd extension
npm ci
npm run build            # Chrome/Edge
npm run build:firefox    # Firefox（详见 extension/FIREFOX.md；zhaopin MAIN-world 需 FF 128+）
```

- **Chrome/Edge**：`chrome://extensions` → 开发者模式 → 加载已解压 → 选 `extension/` 目录（或解压 CI 工件 `talentforge-extension-v*-chrome.zip` 后选解压目录——zip 根即自包含扩展）
- **Firefox**：`about:debugging` → 此 Firefox → 临时载入附加组件 → 选 `extension/dist-firefox/manifest.json`

之后正常浏览 Boss 直聘搜索页 / B站 / 知乎：岗位卡片自动入库（`job_url` 去重），点击/搜索/滚动事件入库（`event_id` 幂等，30-60s 批量上报）。合规红线：只读采集、不绕过验证码、命中风控人工处理。

## 启动

```bash
python -m uvicorn talentforge.api.app:create_app --factory --port 8420
```

浏览器打开 http://127.0.0.1:8420/ 。默认离线 fixtures 假数据开箱即用；URL 加 `?real=1`（或 localStorage 置 `tf_real=1`）切真后端（真实 LLM + 读写 SQLite/画像文件）。

| 视图 | 路由 | 做什么 |
|---|---|---|
| 对话首页 | `#/chat` | 陪伴入口：聊天 + 内嵌卡片（DecisionCard/ClaimCard/RiskNote/ReflectivePrompt），触发决策、沉淀 trial 主张、反思写回画像 |
| 决策工作台 | `#/jobs` | 岗位三态列表（apply/hold/skip）+ 筛选 + 详情（理由链/风险/gap 补短板）+ 生成报告 + 记录投递行为 |
| 画像面板 | `#/profile` | 待定池主张确认/驳回 + 叙事/效用双轨 + 八格结构位置 + 作品主张（强/普通/弱徽章）+ 简历校对 + 导出 |
| 平台源 | `#/sources` | Boss 采集配置 + GitHub/Gitee/arXiv 作品源拉取 |
| 探索器 | `#/explore` | 方向卡快照 → 交叉方向识别（诚实降置信）→ 跳对话深谈 |
| LLM 设置 | `#/llm` | base_url/model/api_key 配置（掩码读回，永不回传明文）+ 连接测试 |
| 简历产出 | `/cv` | A4 排版简历（作品按信号强度排序），打印/导出 PDF |

Primitive Showcase（设计原语三断点验证）：http://127.0.0.1:8420/showcase.html

## CLI

```bash
talentforge serve-api --host 127.0.0.1 --port 8420   # FastAPI 服务（同 uvicorn 入口）
talentforge report --profile docs/demo/profile.json --query 后端工程师 --city 深圳 \
  --db data/talentforge.db                            # 消费库内岗位跑决策报告（JSON 到 stdout）
talentforge profile-build --name 张三 --resume-file resume.pdf \
  --explicit-json '{"skills":["python"]}'             # 简历 bootstrap 画像
talentforge competency --role 后端 --level junior --jd-file jd.txt
talentforge decide --market-fit high --growth-fit high   # 三元决策纯函数试用
talentforge export --out decisions.json              # 决策历史 + 岗位 + 画像快照导出（回测地基）
```

> 注意：`report` 消费**库内岗位**（来自扩展采集）。空库产出空报告——先完成扩展采集。离线演示可用 `--offline-file talentforge/sources/fixtures/boss_search_page.html --db /tmp/tf.db` 直接喂本地 HTML。

### 报告输出字段

报告为 JSON，`summary` 给出计数，`items` 逐岗列出：

| 字段 | 含义 |
|---|---|
| `summary.n_jobs / n_apply / n_hold / n_skip` | 评估岗位总数 / 建议投递 / 暂缓 / 建议跳过 |
| `items[].verdict` | 三元决策：`apply` / `hold` / `skip` |
| `items[].reason` | 决策理由（粗匹配的推理摘要） |
| `items[].risk_hits` | 命中的结构性风险标签清单（如 `996 工作制`），空为未命中 |
| `items[].reflective_question` | 一句反思性反问（基于风险命中或缺失维度） |

### 离线演示（无需浏览器 / 无需插件）

```bash
# 1) 造几条浏览事件 JSONL（每行一个事件），入库
.venv/bin/talentforge events-ingest events.jsonl --db /tmp/m2b-demo.db

# 2) 从事件表消费最近事件，推断 trial 主张并写回画像文件（"画像自长"链路）
.venv/bin/talentforge profile-update --profile docs/demo/profile.json --limit 5 --db /tmp/m2b-demo.db
```

## 里程碑功能

### M4 反馈闭环（显示性偏好回流）

记录真实求职行为 → 偏好序自动微调 → 画像越用越准。工作台"我的行动"记录投递/跳过/结果；apply + offer/interview → 薪资段位自动升 1 位；数据落 `data/feedback_log.json`（幂等），偏好写回画像。规则版无 LLM 参与偏好（D18 人机边界）。

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/feedback/events` | POST | 记录决策/结果，驱动偏好回流 + 叙事修正 |
| `/api/feedback/events?limit=50` | GET | 最近回流条目（倒序） |
| `/api/feedback/summary` | GET | 决策分布统计 |

### M5 作品源 + 简历产出（GitHub/Gitee/arXiv）

拉取公开作品 → 信号分级（D24：持续 commit 的原创仓库/顶会一作 = 强信号；fork 按增量衡量 D27；LLM 证据分类探针 D29）→ verified 主张入画像 → A4 简历（`/cv`）。

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/work/fetch` | POST | 拉取 `{github_user, gitee_user, arxiv_author}`（任选）并入库 |
| `/api/work/artifacts` | GET | 作品列表 + 驳回清单 |
| `/api/work/claims` | POST | 作品 → verified 主张写入画像 |
| `/api/work/dismiss` | POST | 驳回作品 |

GitHub 未认证限流 60 请求/时；`TALENTFORGE_GITHUB_TOKEN` 可升至 5000/时。

### M6 信号投资（gap → 项目推荐）

工作台 gap（如"缺 K8s 实践"）→ GitHub 搜优质 repo → "信号投资建议"卡片（参与即低成本积累强信号）。`/api/suggest`（失败结果缓存 24h）+ `/api/suggest/for-job`。

### M7 探索器（方向快照）

`#/explore`：技术资产盘点快照 → 三口径方向卡 → 识别交叉方向（低置信诚实标注）→ 跳对话深谈。`/api/explore`（snapshot/directions/asset-brief）。

## 测试

```bash
.venv/bin/pytest                                   # Python 全量（后端 + 契约 + 打包回归）
cd extension && npm test                           # 扩展 vitest
node --test web/tests/chat.test.mjs web/tests/jobs.test.mjs web/tests/profile.test.mjs \
  web/tests/sources.test.mjs web/tests/explore.test.mjs web/tests/llm.test.mjs   # Web 渲染断言
```
