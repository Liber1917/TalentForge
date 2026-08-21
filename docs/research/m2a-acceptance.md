# M2a 验收笔记 — Boss 岗位链路

> 验收依据：`docs/spec-m2a-jobs.md` §验收（登录授权下抓 ≥20 条；报告对 ≥10 岗位给出三元决策）。
> 验收日期：2026-08-21。执行人：agentic worker（Task 7）。
> 结论速览：**离线演示验收通过（已复现，记录见 §1）；真实验收标记 pending-user——需用户授权 cookie 后方可执行（§2），不阻塞本里程碑收尾。**

---

## 1. 离线演示验收（已通过，可复现）

**命令：**

```bash
talentforge report --profile docs/demo/profile.json --query 后端工程师 --city 深圳 \
  --offline-file talentforge/sources/fixtures/boss_search_page.html --db /tmp/tf_m2a_accept.db
```

- fixture：`talentforge/sources/fixtures/boss_search_page.html`（5 张卡：3 张 `.job-card-wrapper` + 2 张 `.job-card-box` 回退链变体）。
- 匹配走真实 LLM（OpenCode 本地凭据回退已通）；存库走 `--db` 指定的临时 SQLite。

**实测输出（summary 计数）：**

```
n_jobs=5  n_apply=1  n_hold=4  n_skip=0
```

**items 实测片段（每项 verdict/reason/risk_hits/reflective_question 齐全）：**

```json
{
  "title": "Python 后端工程师", "company": "星辰科技", "verdict": "apply",
  "reason": "候选人具备Python、后端开发、分布式系统技能，与岗位要求高度匹配",
  "risk_hits": [], "reflective_question": "这份工作推进你的系统设计深度吗？"
},
{
  "title": "高级后端开发（Java）", "company": "云帆信息", "verdict": "hold",
  "reason": "候选人技能为Python、后端开发、分布式系统，岗位要求Java和MySQL，核心语言不匹配，市场契合度低",
  "risk_hits": [], "reflective_question": "岗位要求 Java，这是你想补的方向吗？"
}
```

**落库核验：** `SELECT COUNT(*) FROM jobs` = **5**，job_url 以 `https://www.zhipin.com/job_detail/...` 唯一入库。

**验收判定：** ✅ 通过——5 岗全部入库、5 项三元决策完整，覆盖 apply/hold 两档（skip 档在测试套件 `tests/test_report.py` 中以 996 命中 deal-breaker 路径覆盖）。

---

## 2. 真实抓取验收（pending-user，需用户授权 cookie）

当前环境无 Boss 登录 cookie（无 `TALENTFORGE_BOSS_COOKIE` env、无 `~/.jobclaw/cookies/boss.json`），且无 `playwright install chromium` 内核，故真实抓取**不可自动执行**，按计划标记 **pending-user**，不阻塞。

**待用户授权后执行：**

```bash
export TALENTFORGE_BOSS_COOKIE="wt2=...; wbg=..."   # 或经 jobclaw 登录生成 ~/.jobclaw/cookies/boss.json
talentforge report --profile docs/demo/profile.json --query 后端工程师 --city 深圳 --limit 20
```

**验收口径（spec §验收）：**

| 指标 | 口径 |
|---|---|
| 入库条数 | ≥20 条（jobs 表按 job_url 去重） |
| 决策覆盖 | ≥10 岗位给出三元决策（apply/hold/skip） |
| 验证码 | 命中即 `CaptchaDetectedError` 暂停报错，按合规红线等人工（不绕过） |

**验收执行清单：**
- [ ] 用户授权 cookie（env 或 jobclaw 登录文件）
- [ ] `playwright install chromium` 完成浏览器内核下载
- [ ] 跑上述命令，核对入库 ≥20、决策 ≥10
- [ ] 记录真实 summary 计数回填本节

---

## 3. 本次离线验收实测数据

| 计数 | 值 |
|---|---|
| n_jobs（评估岗位数） | 5 |
| n_apply（建议投递） | 1 |
| n_hold（暂缓） | 4 |
| n_skip（建议跳过） | 0 |
| 入库 jobs 行数 | 5 |
| 去重异常（重复 job_url） | 0 |
