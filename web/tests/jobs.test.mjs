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
