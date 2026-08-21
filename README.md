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
