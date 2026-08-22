/* =========================================================
   profile.js 渲染断言（node:test + vm，无第三方依赖）
   在 Node 中加载 web/js/views/profile.js（纯渲染函数），
   用 fixture 数据断言三轨内容 / 待定池 ClaimCard / 八格 /
   diff 视图 / 转义 / 防御性。
   运行：node --test web/tests/profile.test.mjs
   ========================================================= */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

globalThis.window = globalThis;
const src = readFileSync(new URL("../js/views/profile.js", import.meta.url), "utf8");
vm.runInThisContext(src);
const Profile = globalThis.TalentForgeProfile;

const FIXTURE = Profile.LOCAL_FIXTURE_PROFILE;

/* ---------- 待定池 tab ---------- */

test("renderPoolTab trial 主张渲染 ClaimCard 含确认/驳回按钮与置信", () => {
  const html = Profile.renderPoolTab(FIXTURE.narrative_claims);
  assert.match(html, /status-pill--trial/);
  assert.match(html, />待验证</);
  assert.match(html, /置信 90%/);
  assert.match(html, /置信 95%/);
  assert.match(html, /证据 0/);
  assert.match(html, /data-action="claim-confirm"/);
  assert.match(html, /data-action="claim-reject"/);
  assert.match(html, /异步编程技术有深入学习的兴趣/);
  assert.match(html, /Raft、Paxos/);
  assert.match(html, /evidence-chain/);
});

test("renderPoolTab active 折叠区标签与归档区", () => {
  const html = Profile.renderPoolTab(FIXTURE.narrative_claims);
  assert.match(html, /已确认 1 条/);
  assert.match(html, /status-pill--active/);
  assert.match(html, />已确认</);
  assert.doesNotMatch(html, /已归档/);
  assert.doesNotMatch(html, /status-pill--archived/);

  const withArchived = Profile.renderPoolTab([
    ...FIXTURE.narrative_claims,
    { claim_id: "c-arch", text: "旧主张", state: "archived", evidence_count: 0, confidence: 0.5 },
  ]);
  assert.match(withArchived, /已归档 1 条/);
  assert.match(withArchived, /status-pill--archived/);
});

test("renderPoolTab 无 trial 主张时输出空态文案", () => {
  const html = Profile.renderPoolTab([
    { claim_id: "a", text: "已确认", state: "active", evidence_count: 1, confidence: 0.9 },
  ]);
  assert.match(html, /还没有待验证的主张/);
  assert.doesNotMatch(html, /data-action="claim-confirm"/);
});

test("countTrialClaims 只统计 trial 态主张", () => {
  assert.equal(Profile.countTrialClaims(FIXTURE.narrative_claims), 3);
  assert.equal(Profile.countTrialClaims([]), 0);
  assert.equal(Profile.countTrialClaims(null), 0);
});

/* ---------- 叙事轨 ---------- */

test("renderNarrativeTab 含 identity 引言 / values 标签组 / deep_drives", () => {
  const html = Profile.renderNarrativeTab(FIXTURE.narrative);
  assert.match(html, /narrative__identity/);
  assert.match(html, /深耕后端基础设施的工程师/);
  assert.match(html, /tag-pill/);
  assert.match(html, /技术深度/);
  assert.match(html, /工作生活平衡/);
  assert.match(html, /长期成长/);
  assert.match(html, /深层驱动/);
  assert.match(html, /系统设计深度/);
});

test("renderNarrativeTab 缺失字段时不抛错（防御性）", () => {
  const html = Profile.renderNarrativeTab({});
  assert.equal(html.includes("undefined"), false);
  const empty = Profile.renderNarrativeTab(null);
  assert.equal(empty.includes("undefined"), false);
});

/* ---------- 效用轨 ---------- */

test("renderUtilityTab 渲染偏好排序（薪资 40万以上 > 30-40万 > 20-30万）", () => {
  const html = Profile.renderUtilityTab(FIXTURE.utility_preferences);
  assert.match(html, />薪资</);
  assert.match(html, /40万以上/);
  assert.match(html, /30-40万/);
  assert.match(html, /20-30万/);
  assert.match(html, /pref-row__arrow/);
  const salary = FIXTURE.utility_preferences.salary.ordering;
  assert.ok(html.indexOf(salary[0]) < html.indexOf(salary[1]), "ordering 保持优先级顺序");
  assert.ok(html.indexOf(salary[1]) < html.indexOf(salary[2]), "ordering 保持优先级顺序");
});

test("renderUtilityTab 空偏好输出提示", () => {
  const html = Profile.renderUtilityTab({});
  assert.match(html, /还没有记录效用偏好/);
});

test("renderUtilityTab evidence 非空追加决策回流小字；空数组/缺字段不显示（M4）", () => {
  const prefs = {
    salary: {
      attribute: "salary",
      ordering: ["40万以上", "30-40万", "20-30万"],
      evidence: ["2026-08-22 apply 观澜数据(30-45K·14薪)", "2026-08-21 apply 睿达网络(28-45K·15薪)"],
    },
    work_mode: { attribute: "work_mode", ordering: ["弹性工时"], evidence: [] },
    tech_stack: { attribute: "tech_stack", ordering: ["Python"] },
  };
  const html = Profile.renderUtilityTab(prefs);
  assert.match(html, /pref-row__evidence/);
  assert.match(html, /（含 2 次决策回流）/);
  /* 小字位于 ordering 之后 */
  assert.ok(html.indexOf("20-30万") < html.indexOf("（含 2 次决策回流）"));
  /* evidence 数组只出现一次（空数组与缺字段均不渲染） */
  assert.equal((html.match(/pref-row__evidence/g) || []).length, 1);
  const noEvidence = Profile.renderUtilityTab(FIXTURE.utility_preferences);
  assert.doesNotMatch(noEvidence, /pref-row__evidence/);
  assert.doesNotMatch(noEvidence, /决策回流/);
  const emptyArr = Profile.renderUtilityTab({ salary: { attribute: "salary", ordering: ["40万以上"], evidence: [] } });
  assert.doesNotMatch(emptyArr, /pref-row__evidence/);
});

/* ---------- 结构位置 ---------- */

test("renderStructuralTab 八格标签齐全 + 保留工资格式化", () => {
  const html = Profile.renderStructuralTab(FIXTURE.structural_position);
  for (const label of [
    "现金流缓冲",
    "身份/阶段约束",
    "城市约束",
    "家庭责任",
    "支持网络",
    "经济独立",
    "家庭反哺",
    "定价底牌",
  ]) {
    assert.match(html, new RegExp(label), `应含八格标签 ${label}`);
  }
  assert.match(html, /约6个月/);
  assert.match(html, /¥30–35万\/年/);
  assert.match(html, />否</); /* family_payback=false */
  assert.match(html, /eight-grid/);
  assert.match(html, /2 名前同事在内推圈/);
});

test("renderStructuralTab 附加区块（剥削敏感带/再生产账单/流动性）", () => {
  const html = Profile.renderStructuralTab(FIXTURE.structural_position);
  assert.match(html, />剥削敏感带</);
  assert.match(html, /硬边界 · 不可妥协/);
  assert.match(html, /996/);
  assert.match(html, />再生产账单</);
  assert.match(html, /月租 3500/);
  assert.match(html, /技能半衰期/);
  assert.match(html, />流动性与时点</);
  assert.match(html, /敢裸辞/);
  assert.match(html, /骑驴找马/);
});

test("renderStructuralTab market_assessment 存在则标注待数据积累（D17 市场侧灰置）", () => {
  const withMarket = Profile.renderStructuralTab(FIXTURE.structural_position);
  assert.match(withMarket, /待岗位数据积累后启用/);
  assert.match(withMarket, /eight-market/);
  const noMarket = Profile.renderStructuralTab({ cash_buffer: "约6个月" });
  assert.doesNotMatch(noMarket, /待岗位数据积累后启用/);
});

test("renderStructuralTab 缺格值输出未填写占位，空对象不抛错", () => {
  const html = Profile.renderStructuralTab({ cash_buffer: "约6个月" });
  assert.match(html, /未填写/);
  const empty = Profile.renderStructuralTab({});
  assert.equal(empty.includes("undefined"), false);
  const nul = Profile.renderStructuralTab(null);
  assert.equal(nul.includes("undefined"), false);
});

/* ---------- 简历校对 ---------- */

test("renderResumeReview 渲染 抽取 vs 原文 diff 视图与确认按钮", () => {
  const html = Profile.renderResumeReview(Profile.LOCAL_FIXTURE_RESUME_REVIEW);
  assert.match(html, /resume-review/);
  assert.match(html, /resume_demo_2026\.pdf/);
  assert.match(html, />原文</);
  assert.match(html, />抽取</);
  assert.match(html, /三年分布式系统经验/);
  assert.match(html, /Python · Go · 分布式系统 · 消息队列/);
  assert.match(html, /data-action="review-confirm"/);
});

test("renderResumeReview 无数据时输出未上传简历占位", () => {
  const html = Profile.renderResumeReview(null);
  assert.match(html, /未上传简历/);
  const empty = Profile.renderResumeReview(undefined);
  assert.match(empty, /未上传简历/);
});

/* ---------- 防御性：空 profile ---------- */

test("空 profile / 缺失字段渲染不抛错且无 undefined 字样", () => {
  const p = {};
  const pool = Profile.renderPoolTab(p.narrative_claims);
  const narrative = Profile.renderNarrativeTab(p.narrative);
  const utility = Profile.renderUtilityTab(p.utility_preferences);
  const structural = Profile.renderStructuralTab(p.structural_position);
  for (const html of [pool, narrative, utility, structural]) {
    assert.equal(html.includes("undefined"), false);
    assert.equal(html.includes("null"), false);
  }
  assert.equal(Profile.countTrialClaims(undefined), 0);
});

/* ---------- XSS ---------- */

test("XSS：claim 文本/八格值含脚本一律转义", () => {
  const evilClaim = {
    claim_id: "c-evil",
    text: '<script>alert(1)</script><img src=x onerror=alert(2)>',
    state: "trial",
    evidence_count: 0,
    confidence: 0.5,
    sources: [{ kind: "behavior", ref: "demo", at: "" }],
  };
  const poolHtml = Profile.renderPoolTab([evilClaim]);
  assert.match(poolHtml, /&lt;script&gt;/);
  assert.doesNotMatch(poolHtml, /<script>/);
  assert.doesNotMatch(poolHtml, /<img src=x/);

  const structural = Profile.renderStructuralTab({ cash_buffer: '<img src=x onerror="alert(1)">' });
  assert.match(structural, /&lt;img/);
  assert.doesNotMatch(structural, /<img src=x/);

  const narrative = Profile.renderNarrativeTab({ identity: '<b>粗体</b>' });
  assert.doesNotMatch(narrative, /<b>粗体<\/b>/);
});

test("esc / clip / fmtAt 工具行为正确", () => {
  assert.equal(Profile.esc(`<a href="x">&`), "&lt;a href=&quot;x&quot;&gt;&amp;");
  assert.equal(Profile.clip("abc", 2), "ab…");
  assert.equal(Profile.clip("abc", 10), "abc");
  assert.match(Profile.fmtAt("2026-08-21T09:04:00+00:00"), /^\d{2}-\d{2} \d{2}:\d{2}$/);
  assert.equal(Profile.fmtAt(""), "");
});

test("fmtValue 格式化 布尔/数组/对象/保留工资", () => {
  assert.equal(Profile.fmtValue(false), "否");
  assert.equal(Profile.fmtValue(["深圳", "珠三角"]), "深圳、珠三角");
  assert.equal(Profile.fmtValue({ min_annual: 300000, max_annual: 350000, currency: "CNY" }), "¥30–35万/年（CNY）");
  assert.equal(Profile.fmtValue(null), "");
  assert.equal(Profile.fmtValue({ a: 1, b: "x" }), "a：1；b：x");
  assert.equal(
    Profile.fmtValue({ kind: "前同事", note: "可提供内推" }),
    "前同事：可提供内推",
    "support_network 的 kind/note 对象应中文化展示"
  );
});

/* ---------- 本地假数据 ---------- */

test("本地画像 fixture 含三轨 + 3 trial + 1 active", () => {
  assert.equal(FIXTURE.narrative.identity, "深耕后端基础设施的工程师");
  assert.ok(Array.isArray(FIXTURE.narrative.values) && FIXTURE.narrative.values.length >= 3);
  assert.equal(Object.keys(FIXTURE.utility_preferences).length, 5);
  assert.equal(Profile.countTrialClaims(FIXTURE.narrative_claims), 3);
  assert.equal(FIXTURE.narrative_claims.filter((c) => c.state === "active").length, 1);
});

/* ---------- partial 骨架 ---------- */

test("partials/profile.html 含四 tab + 面板 + 导出按钮骨架（ARIA tab 模式）", () => {
  const partial = readFileSync(new URL("../partials/profile.html", import.meta.url), "utf8");
  assert.match(partial, /role="tablist"/);
  assert.match(partial, /data-tab="pool"/);
  assert.match(partial, /data-tab="narrative"/);
  assert.match(partial, /data-tab="utility"/);
  assert.match(partial, /data-tab="structural"/);
  assert.match(partial, /role="tabpanel"/);
  assert.match(partial, /aria-selected="true"/);
  assert.match(partial, /id="profile-export"/);
  assert.match(partial, /id="profile-name"/);
  assert.match(partial, /id="profile-identity"/);
  assert.match(partial, /id="profile-resume"/);
});
