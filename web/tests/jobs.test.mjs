/* =========================================================
   jobs.js 渲染/筛选断言（node:test + vm，无第三方依赖）
   在 Node 中加载 web/js/views/jobs.js（纯渲染/筛选函数），
   用 8 岗位 fixture 断言列表/详情/筛选/统计/转义/空态。
   运行：node --test web/tests/jobs.test.mjs
   ========================================================= */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

globalThis.window = globalThis;
const src = readFileSync(new URL("../js/views/jobs.js", import.meta.url), "utf8");
vm.runInThisContext(src);
const Jobs = globalThis.TalentForgeJobs;

const FIXTURE = Jobs.LOCAL_FIXTURE_JOBS;

/* ---------- 列表渲染 ---------- */

test("renderJobList 覆盖三态徽章、公司名与风险标签", () => {
  const html = Jobs.renderJobList(FIXTURE, {});
  assert.match(html, /verdict-badge--apply/);
  assert.match(html, /verdict-badge--hold/);
  assert.match(html, /verdict-badge--skip/);
  assert.match(html, />投</);
  assert.match(html, />观望</);
  assert.match(html, />不投</);
  assert.match(html, /观澜数据/);
  assert.match(html, /星辰科技/);
  assert.match(html, /云帆信息/);
  assert.match(html, /深圳·福田/);
  assert.match(html, /25-50K·16薪/);
  assert.match(html, /risk-tag/);
  assert.match(html, /card--clickable/);
  assert.match(html, /data-job-url="https:\/\/www\.zhipin\.com\/job_detail\/data_1006\.html"/);
});

test("renderJobRow 选中态输出 is-active 与 aria-current", () => {
  const job = FIXTURE[0];
  const sel = Jobs.renderJobRow(job, { selected: true });
  const unsel = Jobs.renderJobRow(job, { selected: false });
  assert.match(sel, /is-active/);
  assert.match(sel, /aria-current="true"/);
  assert.doesNotMatch(unsel, /is-active/);
  assert.doesNotMatch(unsel, /aria-current="true"/);
});

test("renderJobList 无风险岗位不输出 risk-tag，有风险岗位输出", () => {
  const none = Jobs.renderJobRow(FIXTURE[0]); /* 观澜数据 risk_hits=[] */
  const some = Jobs.renderJobRow(FIXTURE[2]); /* 星辰科技 risk_hits=[996] */
  assert.doesNotMatch(none, /risk-tag/);
  assert.match(some, /risk-tag/);
  assert.match(some, /996 工作制/);
});

/* ---------- 详情渲染 ---------- */

test("renderJobDetail 含理由、风险 note、gap 与 remediation", () => {
  const html = Jobs.renderJobDetail(FIXTURE[2]); /* 星辰科技：risk + gap + evidence */
  assert.match(html, /verdict-badge--hold/);
  assert.match(html, /星辰科技/);
  assert.match(html, /25-50K·16薪/);
  assert.match(html, /决策理由/);
  assert.match(html, /与硬边界冲突/);
  assert.match(html, /risk-note/);
  assert.match(html, /为什么是风险/);
  assert.match(html, /996 工作制/);
  assert.match(html, /补短板/);
  assert.match(html, /能力差距/);
  assert.match(html, /建议动作/);
  assert.match(html, /K8s 容器编排/);
  assert.match(html, /若谈薪资需先确认加班口径/);
  assert.match(html, /chat-about-job/);
  assert.match(html, /聊聊这个岗位/);
  assert.match(html, /打开 JD 原文/);
});

test("renderJobDetail 有 evidence 时渲染理由链；evidence 缺省时隐藏", () => {
  const withEv = Jobs.renderJobDetail(FIXTURE[2]); /* 星辰科技有 evidence */
  const noEv = Jobs.renderJobDetail(FIXTURE[0]); /* 观澜数据无 evidence */
  assert.match(withEv, /evidence-chain/);
  assert.match(withEv, /理由链 · 2 条/);
  assert.match(withEv, /evidence-item__kind/);
  assert.doesNotMatch(noEv, /evidence-chain/);
});

test("renderJobDetail 无 risk_hits 时不输出 risk-note", () => {
  const html = Jobs.renderJobDetail(FIXTURE[0]); /* 观澜数据 risk_hits=[] */
  assert.doesNotMatch(html, /risk-note/);
});

test("renderRiskNote 无 why 字段时给通用知情文案", () => {
  const hit = { key: "996", label: "996 工作制" };
  const html = Jobs.renderRiskNote(hit);
  assert.match(html, /risk-note/);
  assert.match(html, /996 工作制/);
  assert.match(html, /为什么是风险/);
  assert.match(html, /结构性风险点/);
  /* 自定义 why 优先 */
  const withWhy = Jobs.renderRiskNote({ key: "x", label: "X", why: "自定义解释" });
  assert.match(withWhy, /自定义解释/);
  assert.doesNotMatch(withWhy, /结构性风险点/);
});

/* ---------- 反馈行（M4 spec §3） ---------- */

test("renderFeedbackRow 未记录态：三轻量按钮 + outcome 四按钮默认隐藏", () => {
  const html = Jobs.renderFeedbackRow(FIXTURE[0], null);
  assert.match(html, /feedback-row/);
  assert.match(html, /feedback-row__label/);
  assert.match(html, /data-action="feedback-decided" data-verdict="apply"/);
  assert.match(html, /data-action="feedback-decided" data-verdict="skip"/);
  assert.match(html, /data-action="feedback-outcome-toggle"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, />我已投递</);
  assert.match(html, />我跳过了</);
  assert.match(html, />记录结果</);
  assert.match(html, /btn--ghost btn--sm/);
  /* outcome 四小按钮组存在但整体 hidden */
  const group = html.match(/<div class="feedback-outcomes"[^>]*>/);
  assert.ok(group, "应含 feedback-outcomes 组");
  assert.match(group[0], /hidden/);
  for (const [key, label] of [
    ["interview", "面试中"],
    ["rejected", "已拒"],
    ["offer", "offer"],
    ["no_response", "无回音"],
  ]) {
    assert.match(html, new RegExp(`data-action="feedback-outcome" data-outcome="${key}"`));
    assert.match(html, new RegExp(`>${label}<`));
  }
  /* 未记录态不含徽章与改按钮 */
  assert.doesNotMatch(html, /已记录：/);
  assert.doesNotMatch(html, /feedback-edit/);
});

test("renderFeedbackRow 已记录态：徽章文本 + 改按钮回未记录态", () => {
  const fb = { verdict: "apply", outcome: null, at: new Date(2026, 7, 22, 10, 30) };
  const html = Jobs.renderFeedbackRow(FIXTURE[0], fb);
  assert.match(html, /status-pill status-pill--active/);
  assert.match(html, /已记录：投递 08-22/);
  assert.match(html, /data-action="feedback-edit"/);
  assert.match(html, /feedback-row--done/);
  assert.doesNotMatch(html, /feedback-decided/);
  assert.doesNotMatch(html, /feedback-outcomes/);
  /* skip/hold 的中文映射 */
  const skip = Jobs.renderFeedbackRow(FIXTURE[0], { verdict: "skip", outcome: null, at: new Date(2026, 7, 22) });
  assert.match(skip, /已记录：跳过 08-22/);
});

test("renderJobDetail 第二参数 feedback 联动反馈行（缺省为未记录态）", () => {
  const plain = Jobs.renderJobDetail(FIXTURE[0]);
  assert.match(plain, /feedback-decided/);
  assert.match(plain, /聊聊这个岗位[\s\S]*feedback-row/);
  const done = Jobs.renderJobDetail(FIXTURE[0], { verdict: "apply", outcome: null, at: new Date(2026, 7, 22) });
  assert.match(done, /已记录：投递 08-22/);
});

test("XSS：反馈行 verdict/岗位标题注入一律转义", () => {
  const evilVerdict = { verdict: '<script>alert(1)</script>', outcome: null, at: new Date(2026, 7, 22) };
  const html = Jobs.renderFeedbackRow(FIXTURE[0], evilVerdict);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  const evilJob = { ...FIXTURE[0], title: '"><img src=x onerror=alert(2)>' };
  for (const out of [Jobs.renderFeedbackRow(evilJob, null), Jobs.renderFeedbackRow(evilJob, evilVerdict)]) {
    assert.doesNotMatch(out, /<img src=x/);
    assert.match(out, /&quot;&gt;&lt;img src=x/);
  }
});

test("fmtDay 输出 MM-DD（Date/ISO 兼容，非法值空串）", () => {
  assert.equal(Jobs.fmtDay(new Date(2026, 7, 22)), "08-22");
  assert.equal(Jobs.fmtDay(new Date(2026, 0, 3)), "01-03");
  assert.equal(Jobs.fmtDay(""), "");
  assert.equal(Jobs.fmtDay(null), "");
});

/* ---------- 筛选逻辑（纯函数） ---------- */

test("filterJobs 空筛选返回全部 8 个", () => {
  assert.equal(Jobs.filterJobs(FIXTURE, {}).length, 8);
});

test("filterJobs q 按标题/公司/地点模糊匹配（大小写不敏感）", () => {
  assert.equal(Jobs.filterJobs(FIXTURE, { q: "python" }).length, 2);
  assert.equal(Jobs.filterJobs(FIXTURE, { q: "星辰" }).length, 1);
  assert.equal(Jobs.filterJobs(FIXTURE, { q: "南山" }).length, 4);
  assert.equal(Jobs.filterJobs(FIXTURE, { q: "不存在" }).length, 0);
});

test("filterJobs city / verdict 组合过滤", () => {
  assert.equal(Jobs.filterJobs(FIXTURE, { city: "深圳·南山" }).length, 4);
  assert.equal(Jobs.filterJobs(FIXTURE, { verdict: "apply" }).length, 2);
  assert.equal(Jobs.filterJobs(FIXTURE, { verdict: "hold" }).length, 2);
  assert.equal(Jobs.filterJobs(FIXTURE, { verdict: "skip" }).length, 4);
  const combo = Jobs.filterJobs(FIXTURE, { city: "深圳·南山", verdict: "skip", q: "星" });
  assert.equal(combo.length, 1);
  assert.equal(combo[0].company, "星环科技");
});

test("collectCities 从数据去重生成城市选项", () => {
  const cities = Jobs.collectCities(FIXTURE);
  assert.equal(cities.length, 4);
  for (const c of ["深圳·福田", "深圳·南山", "深圳·宝安", "深圳·龙华"]) {
    assert.ok(cities.includes(c), `应包含 ${c}`);
  }
  assert.deepEqual(new Set(cities).size, cities.length);
});

test("countStats 统计三态数量", () => {
  assert.deepEqual(Jobs.countStats(FIXTURE), { total: 8, apply: 2, hold: 2, skip: 4 });
  assert.deepEqual(Jobs.countStats([]), { total: 0, apply: 0, hold: 0, skip: 0 });
});

/* ---------- 空态 ---------- */

test("renderJobList 空列表输出筛选空态提示", () => {
  const html = Jobs.renderJobList([], {});
  assert.match(html, /没有符合筛选的岗位/);
  assert.match(html, /jobs-empty/);
});

test("renderEmptyState 无数据时输出引导卡", () => {
  const html = Jobs.renderEmptyState({ hasData: false });
  assert.match(html, /还没有决策数据/);
  assert.match(html, /去对话页聊聊/);
});

/* ---------- XSS ---------- */

test("XSS：岗位标题/理由含脚本时一律转义", () => {
  const evil = {
    ...FIXTURE[0],
    title: '<script>alert(1)</script>',
    reason: '"><img src=x onerror=alert(2)>',
    company: '<b>粗体</b>',
  };
  const row = Jobs.renderJobRow(evil, {});
  const detail = Jobs.renderJobDetail(evil);
  for (const html of [row, detail]) {
    assert.match(html, /&lt;script&gt;/);
    assert.doesNotMatch(html, /<script>/);
    assert.doesNotMatch(html, /<img src=x/);
    assert.doesNotMatch(html, /<b>粗体<\/b>/);
  }
});

test("esc / clip 工具行为正确", () => {
  assert.equal(Jobs.esc(`<a href="x">&`), "&lt;a href=&quot;x&quot;&gt;&amp;");
  assert.equal(Jobs.clip("abc", 2), "ab…");
  assert.equal(Jobs.clip("abc", 10), "abc");
});

/* ---------- partial 骨架 ---------- */

test("partials/jobs.html 含筛选条/双栏/状态容器的骨架", () => {
  const partial = readFileSync(new URL("../partials/jobs.html", import.meta.url), "utf8");
  assert.match(partial, /id="jobs-q"/);
  assert.match(partial, /aria-label="搜索岗位"/);
  assert.match(partial, /id="jobs-city"/);
  assert.match(partial, /aria-label="按城市筛选"/);
  assert.match(partial, /data-verdict-filter="apply"/);
  assert.match(partial, /data-verdict-filter="hold"/);
  assert.match(partial, /data-verdict-filter="skip"/);
  assert.match(partial, /id="jobs-report"/);
  assert.match(partial, /l-split/);
  assert.match(partial, /id="jobs-list"/);
  assert.match(partial, /id="jobs-detail"/);
  assert.match(partial, /id="jobs-status"/);
  assert.match(partial, /id="jobs-count"/);
});

/* ---------- M6 信号投资（gap 对象形态 + 补信号推荐区） ---------- */

test("renderGapBlock 对象形态 gap：skill 粗体/severity 徽章/evidence 小字 + 补信号按钮", () => {
  const job = {
    ...FIXTURE[0],
    gap: [
      { skill: "Kubernetes", severity: "major", evidence: "JD 要求 K8s 部署经验，画像无容器编排记录" },
      { skill: "压测调优", severity: "minor", evidence: "JD 提到全链路压测，画像无性能调优记录" },
    ],
  };
  const html = Jobs.renderGapBlock(job);
  assert.match(html, /gap-item__skill/);
  assert.match(html, /<strong[^>]*>Kubernetes<\/strong>/);
  assert.match(html, /gap-sev gap-sev--major/);
  assert.match(html, /gap-sev gap-sev--minor/);
  assert.match(html, /JD 要求 K8s 部署经验，画像无容器编排记录/);
  assert.match(html, /gap-item__evidence/);
  /* 补信号按钮 + 默认隐藏的推荐区容器 */
  assert.match(html, /data-action="suggest-toggle"/);
  assert.match(html, /data-job-url="https:\/\/www\.zhipin\.com\/job_detail\/data_1006\.html"/);
  assert.match(html, /data-role="suggest-box"/);
  const box = html.match(/<div[^>]*data-role="suggest-box"[^>]*>/);
  assert.ok(box, "应含 suggest-box 容器");
  assert.match(box[0], /hidden/);
  assert.match(html, /aria-expanded="false"/);
});

test("renderGapBlock 字符串数组（fixtures 旧形态）：保持 <li> 兼容渲染", () => {
  const html = Jobs.renderGapBlock(FIXTURE[2]); /* gap: ["K8s 容器编排", "高并发压测"] */
  assert.match(html, /<li>K8s 容器编排<\/li>/);
  assert.match(html, /<li>高并发压测<\/li>/);
  assert.doesNotMatch(html, /gap-item__skill/);
  /* gap 非空 → 有补信号按钮；空 gap（"——" 过滤后为空）→ 无按钮 */
  assert.match(html, /suggest-toggle/);
  assert.doesNotMatch(Jobs.renderGapBlock(FIXTURE[7]), /suggest-toggle/);
});

test("renderJobDetail 对象形态 gap 联动推荐区容器（默认隐藏）", () => {
  const job = { ...FIXTURE[0], gap: [{ skill: "Kubernetes", severity: "major", evidence: "JD 要求" }] };
  const html = Jobs.renderJobDetail(job);
  assert.match(html, /gap-sev--major/);
  assert.match(html, /data-role="suggest-box"/);
  const box = html.match(/<div[^>]*data-role="suggest-box"[^>]*>/);
  assert.ok(box);
  assert.match(box[0], /hidden/);
});

test("renderSuggestBox fixtures：建议卡含 stars/why/meta/外链 noopener", () => {
  const html = Jobs.renderSuggestBox(Jobs.LOCAL_SUGGEST_FIXTURES);
  assert.match(html, /suggest-group__skill/);
  assert.match(html, /suggest-card/);
  assert.match(html, /suggest-card__stars/);
  assert.match(html, /★ \d+/);
  assert.match(html, /suggest-card__why/);
  assert.match(html, /suggest-card__meta/);
  assert.match(html, /\d{4}-\d{2}-\d{2}/);
  assert.match(html, /target="_blank" rel="noopener/);
  assert.match(html, />参与 ↗</);
});

test("renderSuggestBox 兼容 for-job 响应形态；无 gaps 给提示文案", () => {
  assert.match(Jobs.renderSuggestBox({ ok: true, results: Jobs.LOCAL_SUGGEST_FIXTURES }), /suggest-card/);
  assert.match(Jobs.renderSuggestBox({ ok: true, gaps: [] }), /该岗位暂无 gap 分析/);
  assert.match(Jobs.renderSuggestBox([]), /先在对话页跑一次决策/);
});

test("renderSuggestBox description 超 80 字截断", () => {
  const long = "甲".repeat(100);
  const html = Jobs.renderSuggestBox([{
    skill: "S",
    severity: "major",
    suggestions: [{ full_name: "a/b", url: "https://github.com/a/b", stars: 1, description: long, language: "", pushed_at: "", why: "" }],
  }]);
  assert.ok(html.includes("甲".repeat(80)), "应保留前 80 字");
  assert.ok(!html.includes("甲".repeat(81)), "应截断 80 字之后");
  assert.match(html, /…/);
});

test("renderSuggestHint 加载/失败文案（失败用 risk 语义类）", () => {
  assert.match(Jobs.renderSuggestHint("找项目中…"), /找项目中…/);
  assert.match(Jobs.renderSuggestHint("找项目中…"), /suggest-box__hint"/);
  const err = Jobs.renderSuggestHint("推荐失败：后端未启动", "error");
  assert.match(err, /推荐失败：后端未启动/);
  assert.match(err, /suggest-box__hint--error/);
});

test("XSS：推荐区 skill/description/why 与 gap evidence 注入一律转义", () => {
  const evil = [{
    skill: '<script>alert(1)</script>',
    severity: "major",
    evidence: '"><img src=x onerror=alert(2)>',
    suggestions: [{
      full_name: 'evil/repo"><img src=x onerror=alert(3)>',
      url: "https://github.com/evil/repo",
      stars: 120,
      description: '<img src=x onerror=alert(4)>',
      language: "Python",
      pushed_at: "2026-08-01T00:00:00Z",
      why: "<b>bold</b>",
    }],
  }];
  const html = Jobs.renderSuggestBox(evil);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;b&gt;bold&lt;\/b&gt;/);
  /* gap 区块对象形态同样转义 */
  const gapHtml = Jobs.renderGapBlock({ ...FIXTURE[0], gap: evil });
  assert.doesNotMatch(gapHtml, /<script>/);
  assert.doesNotMatch(gapHtml, /<img src=x/);
  assert.match(gapHtml, /&lt;script&gt;/);
});
