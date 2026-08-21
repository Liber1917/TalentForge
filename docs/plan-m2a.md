# M2a Boss 岗位链路 实施计划

> **For agentic workers:** superpowers:subagent-driven-development（Sisyphus 编排，后台派发 implementer，controller 审查+git-master 提交）。

**Goal:** Boss 抓取→归一化→场域风险→粗匹配→三元决策报告，端到端真数据垂直切片。

**Spec:** `docs/spec-m2a-jobs.md`。侦察依据：`docs/research/m2-boss-recon.md`。

## Global Constraints

- Python >=3.10；Playwright 为新依赖（浏览器内核 `playwright install chromium` 需真实下载，用阿里云镜像 pip 包，浏览器下载走官方 CDN 若慢则记录不阻塞纯函数任务）
- 抓取合规红线：只读、登录授权 cookie、验证码检测到即暂停报错（不绕过）、页间随机延迟 5-10s、单 run ≤3 页
- LLM 走既有 EnvLLMClient（auth.json 回退已通）；匹配 prompt 遵守 system 静态约定
- conventional commit；`GIT_MASTER=1`；每 task 一 commit

---

### Task 1: Boss 抓取器核心（纯函数层 + HTML fixture 测试）

**Files:** Create `talentforge/sources/__init__.py`(空)、`talentforge/sources/boss.py`、`talentforge/sources/captcha.py`、`talentforge/sources/fixtures/boss_search_page.html`；Test `tests/test_boss_parse.py`

**Interfaces（Produces）:** `CITY_CODES: dict[str,str]`（深圳/北京/上海/广州/杭州/成都/武汉/西安/南京/长沙 ≥10 城）、`detect_captcha(html_text)->list[str]`（命中关键词清单）、`parse_boss_cards(html, base_url="https://www.zhipin.com")->list[dict]`（原始卡字段 dict）、`parse_salary(text)->dict`（min_annual/max_annual/currency，16薪→月薪×奖金月数）、`build_search_url(query, city, page)->str`

**要点：**
- parse_boss_cards 用 BeautifulSoup（新依赖 bs4）或纯正则——**选 bs4**（选择器回退链需要）；选择器回退链：卡片 `[5 个候选]`、标题/公司/薪资/链接/标签各 ≥2 候选（参照 jobclaw applier 侧模式）
- 薪资：`(\d+)-(\d+)K` + `(\d+)薪`（默认 12），输出**年薪**口径（K→千×月数）
- fixture HTML：手写最小结构（含 3 张卡 + 1 张验证码页变体），放 tests 或 sources/fixtures
- captcha.py 移植 jobclaw 4 关键词（选择器检测在 Playwright 层做，HTML 文本层先做关键词版）

**测试：** fixture 上解析 3 卡（字段齐全/薪资含16薪/去重 href）；验证码页 detect 命中"请完成安全验证"；city 码表查深圳=101280600；parse_salary("25-50K·16薪")→min_annual=400000。
commit: `feat: boss scraper core (parsers, captcha detect, city codes, salary normalization)`

### Task 2: Playwright 抓取循环（浏览器层）

**Files:** Create `talentforge/sources/boss_scraper.py`（类 `BossScraper`）；Modify pyproject（playwright、bs4）；Test `tests/test_boss_scraper.py`（mock Playwright）

**Interfaces:** `BossScraper(settings).scrape(query, city, limit, pages=3) -> list[Job]`；async context manager（仿 jobclaw：`async with BossScraper(s) as scraper`）

**要点：**
- cookie 注入复用 jobclaw 三层优先（env BOSS_COOKIE > ~/.jobclaw/cookies/boss.json > 报错提示 login）——读 jobclaw 的 cookie 文件格式（saved_at+cookies 数组），**但不写 jobclaw 包**，自实现 `load_boss_cookies()`（`talentforge/sources/cookies.py`）
- 页循环：goto build_search_url(page=N) → networkidle → detect_captcha（页面文本）→ 命中即 raise `CaptchaDetectedError`（附页面快照路径）→ parse_boss_cards(page.content()) → 翻页前 `asyncio.sleep(random.uniform(5,10))`
- UA 伪装（jobclaw 同款 Chrome/125 串）；headless 从 env TALENTFORGE_HEADLESS（默认 true）
- 测试：monkeypatch async_playwright 返回 fake browser/page（fixture HTML 作为 content），断言翻页调用、captcha raise、cookie 注入调用

commit: `feat: boss playwright scraper loop (cookie inject, pagination, captcha pause)`

### Task 3: Job 存储 + 风险标记

**Files:** Create `talentforge/storage/__init__.py` 写实、`talentforge/storage/db.py`、`talentforge/sources/normalize.py`；Test `tests/test_storage.py`

**Interfaces:** `init_db(path)->sqlite3.Connection`（建 jobs 表：job_url UNIQUE/source/title/company/location/salary_json/tags_json/description/risk_keys_json/scraped_at）、`upsert_job(conn, job: Job)->bool`（新插入返回 True）、`list_jobs(conn, limit)->list[Job]`；`normalize_to_job(card: dict, city: str)->Job`（含 `scan_risks(text)->list[str]`——关键词：996/大小周/单休/无偿加班/竞业限制/加班费模糊→risk_keys）

**测试：** 内存 db 建表/upsert 去重（同 URL 二次返 False）/list；normalize 含"大小周"JD→risk_keys 命中；薪资 dict→SalaryRange。
commit: `feat: job storage (sqlite upsert/dedupe) + risk key normalization`

### Task 4: 场域最小版（风险信号库）

**Files:** Create `talentforge/field/__init__.py`(空)、`talentforge/field/risks.py`；Test `tests/test_field_risks.py`

**Interfaces:** `STRUCTURAL_RISKS: dict[str, RiskInfo]`（~10 条，RiskInfo=key/label/why（政治经济学解释 2-3 句）/severity）、`assess(job: Job)->dict`（命中 risk_keys→label+why+severity 清单，附 field_notes）

**要点：** why 文案要"知情非说教"（D13/D14：讲清为什么是剥削，不下道德判词）；996/竞业限制定 severity="deal_breaker_candidate"（供 UI 提示与 deal_breakers 对照），其余 "warning"。
**测试：** 命中映射、未命中空、severity 分档。
commit: `feat: minimal field model (structural risk signal library with explanations)`

### Task 5: 粗匹配器（LLM 单跳 → FitLevel）

**Files:** Create `talentforge/matcher/__init__.py`(空)、`talentforge/matcher/coarse.py`；Test `tests/test_coarse_matcher.py`

**Interfaces:** `COARSE_MATCH_SYSTEM_PROMPT`（静态）、`CoarseMatcher(llm).match(profile, job, field_notes)->Match`（async）

**要点：**
- system 静态：角色定义 + 只输出 JSON {"market_fit":"high|low","growth_fit":"high|low","reasoning":[...],"matched":["..."],"missing":["..."]}
- user 按稳定→可变排序：Profile 摘要（verified 硬字段标记 [已验证]/[待验证]）→ Job 摘要 → field_notes
- 输出容错走 extract_json；FitLevel 解析失败默认 low + reasoning 附错因
- 测试：FakeLLM 围栏 JSON→Match 断言；坏 JSON→默认 low

commit: `feat: coarse LLM matcher (two-level fit with verified/unverified marking)`

### Task 6: 决策报告命令（端到端）

**Files:** Create `talentforge/report/__init__.py`(空)、`talentforge/report/generate.py`；Modify `talentforge/cli.py`（report 命令）；Test `tests/test_report.py`

**Interfaces:** `generate_report(profile: Profile, query, city, limit, scraper, matcher, conn)->dict`（jobs→normalize→storage→逐岗 match+field.assess+decide()→报告 dict：summary{n_applied/n_hold/n_skip}+items[{job_id,title,company,verdict,reason,risk_hits,reflective_question}]）；CLI `talentforge report --profile <json> --query <str> --city <str> [--limit 10] [--db path] [--offline-file <html>]`

**要点：** `--offline-file` 直接喂本地 HTML 跳过浏览器（测试/无登录演示用）；reflective_question 从 risk_hits 或 missing 里生成一句（规则模板，M3 换 LLM）；报告 JSON 到 stdout。
**测试：** offline-file + FakeLLM 端到端——fixture HTML→3 卡→3 决策项断言 summary 计数；decide() 集成（风险命中改变 verdict）。
commit: `feat: end-to-end decision report command (scrape->normalize->match->decide)`

### Task 7: 真实验收 + 收尾

**Files:** 无新文件（运行验收）；可能 fixture 微调

**要点：** 用户授权 cookie 后真实跑 `talentforge report --profile docs/demo/profile.json --query "后端工程师" --city 深圳 --limit 20`，验收 ≥20 条入库 ≥10 决策（spec 口径）；无 cookie 时以 --offline-file 演示模式收尾、真实验收标记 pending-user。README 补 M2a 使用节（安装 playwright/登录/跑报告）。
commit: `docs: M2a acceptance notes and README usage`

---

## 自审记录

- Spec 覆盖：spec-m2a §1↔Task1-6、§验收↔Task7、§不在范围 均未越界（无插件/无精排/无市场侧估算）。
- 依赖顺序：T1 纯函数（无浏览器）→T2 依赖 T1 解析器→T3 依赖 domain Job→T4 独立→T5 依赖 llm+domain→T6 汇总。T4 可与 T2 并行（目录不相邻但 controller 串行派发更稳）。
- 已知风险：Playwright chromium 下载可能慢/失败——Task 1/3/4/5 不依赖浏览器，失败不阻塞主线；Task 2/6 的真实浏览器验证可后置 Task 7。
- bs4/playwright 新依赖已列入 Task 2 的 pyproject 修改（Task 1 需要 bs4——移到 Task 1 改 pyproject）。
