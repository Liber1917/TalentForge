/* =========================================================
   explore.js 渲染断言（node:test + vm，无第三方依赖）
   在 Node 中加载 web/js/views/explore.js（纯渲染函数），
   用 fixture 数据断言方向卡结构 / 三口径徽章 / data_backed
   双标记 / 证据链折叠 / 约束碰撞 / 第一步 / 资产盘点四组 /
   转义 / 防御性 / partial 骨架 / 深谈接续（chat.js 握手）。
   运行：node --test web/tests/explore.test.mjs
   ========================================================= */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

globalThis.window = globalThis;
const src = readFileSync(new URL("../js/views/explore.js", import.meta.url), "utf8");
vm.runInThisContext(src);
const Explore = globalThis.TalentForgeExplore;

const FIXTURES = Explore.LOCAL_DIRECTION_FIXTURES;
const [TRACK_CARD, LIFESTYLE_CARD, FIELD_CARD] = FIXTURES;

/* ---------- scope 三态徽章 ---------- */

test("scopeBadgeClass 三口径映射 + 未知口径回退 track", () => {
  assert.equal(Explore.scopeBadgeClass("track"), "scope-badge scope-badge--track");
  assert.equal(Explore.scopeBadgeClass("lifestyle"), "scope-badge scope-badge--lifestyle");
  assert.equal(Explore.scopeBadgeClass("field"), "scope-badge scope-badge--field");
  assert.equal(Explore.scopeBadgeClass("bogus"), "scope-badge scope-badge--track");
  assert.equal(Explore.scopeBadgeClass(""), "scope-badge scope-badge--track");
});

test("renderDirectionCard 三态徽章类名与中文标签各自落位", () => {
  const track = Explore.renderDirectionCard(TRACK_CARD);
  assert.match(track, /class="scope-badge scope-badge--track"/);
  assert.match(track, />赛道</);
  assert.doesNotMatch(track, /scope-badge--lifestyle/);

  const lifestyle = Explore.renderDirectionCard(LIFESTYLE_CARD);
  assert.match(lifestyle, /scope-badge scope-badge--lifestyle/);
  assert.match(lifestyle, />活法</);

  const field = Explore.renderDirectionCard(FIELD_CARD);
  assert.match(field, /scope-badge scope-badge--field/);
  assert.match(field, />场域</);
});

/* ---------- renderDirectionCard 结构 ---------- */

test("renderDirectionCard 卡头/标题/置信/data_backed/深挖按钮齐全", () => {
  const html = Explore.renderDirectionCard(TRACK_CARD);
  assert.match(html, /data-card-id="dir-demo-edge-ai"/);
  assert.match(html, /data-scope="track"/);
  assert.match(html, /direction-card__title[^>]*>边缘 AI 部署</);
  assert.match(html, /置信 72%/);
  assert.match(html, /direction-card__databack--data">数据✓</);
  assert.match(html, /data-action="deep-dive"/);
  assert.match(html, /data-card-title="边缘 AI 部署"/);
  assert.match(html, />深挖这个方向</);
  assert.match(html, /aria-label="深挖方向：/);
});

test("renderDirectionCard why_you 证据链折叠（details/summary + 锚点行）", () => {
  const html = Explore.renderDirectionCard(TRACK_CARD);
  assert.match(html, /<details class="evidence-chain">/);
  assert.match(html, /为什么是你 · 3 条/);
  assert.match(html, /evidence-item__kind">作品</);
  assert.match(html, /evidence-item__kind">画像</);
  assert.match(html, /evidence-item__kind">行为</);
  assert.match(html, /evidence-item__ref">github:demo\/edge-infer</);
  assert.match(html, /142 commits 持续 14 个月/);
});

test("renderDirectionCard 市场验证/差多远/第一步高亮卡逐区块渲染", () => {
  const html = Explore.renderDirectionCard(TRACK_CARD);
  assert.match(html, />市场验证</);
  assert.match(html, /30-60K·15薪/);
  assert.match(html, />差多远</);
  assert.match(html, /缺 1-2 个可复现的部署案例/);
  assert.match(html, /direction-card__step/);
  assert.match(html, />第一步</);
  assert.match(html, /两周内把 edge-infer 整理成带板卡、文档与指标的部署案例/);
  /* 第一步是高亮小卡，不是普通 row */
  assert.ok(html.indexOf("direction-card__step") > html.indexOf("direction-card__row"));
});

test("renderDirectionCard constraint_check 渲染琥珀提示行（多条全渲染）", () => {
  const html = Explore.renderDirectionCard(LIFESTYLE_CARD);
  assert.match(html, /direction-card__constraints/);
  assert.match(html, /role="note"/);
  assert.equal((html.match(/class="direction-card__constraint"/g) || []).length, 2);
  assert.match(html, /⚠ 期权流动性差/);
  assert.match(html, /⚠ 部分初创合同含竞业条款/);

  const none = Explore.renderDirectionCard({ ...TRACK_CARD, constraint_check: [] });
  assert.doesNotMatch(none, /direction-card__constraints/);
});

test("renderDirectionCard data_backed=false 输出 推理≈ 标记（D13 边界诚实）", () => {
  const html = Explore.renderDirectionCard(FIELD_CARD);
  assert.match(html, /direction-card__databack--inferred">推理≈</);
  assert.doesNotMatch(html, /数据✓/);
  assert.match(html, /置信 55%/);
  const flipped = Explore.renderDirectionCard({ ...FIELD_CARD, data_backed: true });
  assert.match(flipped, /数据✓/);
  assert.doesNotMatch(flipped, /推理≈/);
});

/* ---------- LOCAL_DIRECTION_FIXTURES 三口径 ---------- */

test("LOCAL_DIRECTION_FIXTURES 恰好 3 张，三口径各一，字段齐全", () => {
  assert.equal(FIXTURES.length, 3);
  assert.deepEqual(FIXTURES.map((c) => c.scope).sort(), ["field", "lifestyle", "track"]);
  assert.equal(TRACK_CARD.title, "边缘 AI 部署");
  assert.equal(LIFESTYLE_CARD.title, "初创核心工程师");
  assert.equal(FIELD_CARD.title, "上海 vs 新一线");
  for (const c of FIXTURES) {
    assert.ok(c.card_id && c.title);
    assert.ok(Array.isArray(c.why_you) && c.why_you.length >= 2);
    assert.ok(c.market_evidence && c.distance && c.first_step);
    assert.ok(Array.isArray(c.constraint_check) && c.constraint_check.length >= 1);
    assert.ok(typeof c.data_backed === "boolean");
    assert.ok(c.confidence > 0 && c.confidence <= 1);
    for (const e of c.why_you) {
      assert.ok(e.kind && e.ref !== undefined && e.text !== undefined);
    }
  }
});

/* ---------- 列表 / 状态 / 空态 ---------- */

test("renderDirectionsList 渲染全部卡；空数据输出引导文案", () => {
  const html = Explore.renderDirectionsList(FIXTURES);
  assert.equal((html.match(/class="card direction-card"/g) || []).length, 3);
  assert.match(html, /边缘 AI 部署/);
  assert.match(html, /初创核心工程师/);
  assert.match(html, /上海 vs 新一线/);

  const empty = Explore.renderDirectionsList([]);
  assert.match(empty, /还没有方向卡/);
  assert.match(empty, /生成方向快照/);
  assert.doesNotMatch(empty, /direction-card"/);
});

test("renderSnapshotStatus 加载态（书房语气）/ 失败态（risk 色 + 截断）", () => {
  const loading = Explore.renderSnapshotStatus("loading");
  assert.match(loading, /explore-status--loading/);
  assert.match(loading, /role="status"/);
  assert.match(loading, /约 1 分钟/);

  const error = Explore.renderSnapshotStatus("error", "LLM 返回超时");
  assert.match(error, /explore-status--error/);
  assert.match(error, /role="alert"/);
  assert.match(error, /生成失败：LLM 返回超时/);

  const clipped = Explore.renderSnapshotStatus("error", "x".repeat(200));
  assert.match(clipped, /…/);
  assert.equal(Explore.renderSnapshotStatus("unknown"), "");
});

/* ---------- 资产盘点 ---------- */

test("renderAssetBrief 四组紧凑清单：技能簇/强信号/行为兴趣/硬边界", () => {
  const html = Explore.renderAssetBrief(Explore.LOCAL_ASSET_BRIEF);
  assert.match(html, /explore-brief__grid/);
  assert.match(html, /技能簇（作品语言分布）/);
  assert.match(html, /强信号（强作品 \+ 已确认主张）/);
  assert.match(html, /行为兴趣（待验证主张）/);
  assert.match(html, /硬边界（deal breakers \+ 剥削敏感带）/);
  assert.match(html, /Python × 6 仓库/);
  assert.match(html, /C\+\+ × 2 仓库/);
  assert.match(html, /\[github\] edge-infer（C\+\+，142 commits）/);
  assert.match(html, /异步编程技术有深入学习的兴趣/);
  assert.match(html, /<li>996<\/li>/);
  assert.match(html, /href="#\/profile"/);
});

test("renderAssetBrief brief=null 输出占位（含 reason）；空组给暂无记录", () => {
  const html = Explore.renderAssetBrief(null, "暂无画像");
  assert.match(html, /暂无可盘点的资产（暂无画像）/);
  assert.match(html, /role="status"/);
  assert.equal(Explore.renderAssetBrief(null).includes("undefined"), false);

  const sparse = Explore.renderAssetBrief({ skill_clusters: [], strong_signals: [], behavior_interests: [], hard_boundaries: {} });
  assert.equal((sparse.match(/暂无记录/g) || []).length, 4);
});

/* ---------- XSS / 防御性 ---------- */

test("XSS：title/市场/第一步/约束含脚本一律转义（含 data-card-title 属性）", () => {
  const evil = Explore.renderDirectionCard({
    ...TRACK_CARD,
    title: '<script>alert(1)</script>',
    market_evidence: '<img src=x onerror=alert(2)>',
    first_step: '<b>加粗注入</b>',
    constraint_check: ['<script>alert(3)</script>'],
    why_you: [{ kind: "work", ref: '"><iframe>', text: "<script>alert(4)</script>" }],
  });
  assert.match(evil, /&lt;script&gt;/);
  assert.doesNotMatch(evil, /<script>/);
  assert.doesNotMatch(evil, /<img src=x/);
  assert.doesNotMatch(evil, /<b>加粗注入<\/b>/);
  assert.match(evil, /data-card-title="&lt;script&gt;/);
  assert.doesNotMatch(evil, /<iframe>/);
});

test("空数据/脏数据防御：null 条目与空参不抛错且无 undefined 字样", () => {
  assert.equal(Explore.renderDirectionCard(null), "");
  const dirty = Explore.renderDirectionsList([null, {}, TRACK_CARD]);
  assert.equal(dirty.includes("undefined"), false);
  assert.equal((dirty.match(/class="card direction-card"/g) || []).length, 2);
  assert.equal(Explore.renderDirectionsList(null).includes("undefined"), false);
  assert.equal(Explore.renderAssetBrief({}).includes("undefined"), false);
  assert.equal(Explore.esc(`<a href="x">&`), "&lt;a href=&quot;x&quot;&gt;&amp;");
  assert.equal(Explore.clip("abcdef", 3), "abc…");
});

/* ---------- partial 骨架 ---------- */

test("partials/explore.html 与 FALLBACK_PARTIAL 含 页头+盘点区+快照按钮+卡区骨架", () => {
  const partial = readFileSync(new URL("../partials/explore.html", import.meta.url), "utf8");
  for (const doc of [partial, Explore.FALLBACK_PARTIAL]) {
    assert.match(doc, /explore-layout/);
    assert.match(doc, /explore-head__title">方向探索</);
    assert.match(doc, /<details class="explore-brief" id="explore-brief">/);
    assert.match(doc, /id="explore-brief-body"/);
    assert.match(doc, /data-role="explore-brief-body"/);
    assert.match(doc, /data-action="generate-snapshot"/);
    assert.match(doc, />生成方向快照</);
    assert.match(doc, /id="explore-generate"/);
    assert.match(doc, /id="explore-cards"/);
    assert.match(doc, /role="list"/);
    assert.match(doc, /aria-label="方向卡列表"/);
  }
});

/* ---------- 深谈接续（chat.js 握手） ---------- */

const chatSrc = readFileSync(new URL("../js/views/chat.js", import.meta.url), "utf8");
vm.runInThisContext(chatSrc);
const Chat = globalThis.TalentForgeChat;

test("chat.js 深谈接续：buildDeepDiveTurn 含方向摘要上下文与开场提问", () => {
  const turn = Chat.buildDeepDiveTurn("边缘 AI 部署", "track");
  assert.equal(turn.role, "assistant");
  assert.deepEqual(turn.cards, []);
  assert.match(turn.text, /想深挖「边缘 AI 部署」这个方向（口径：赛道）。/);
  assert.match(turn.text, /你最想弄清楚哪一点——市场、准备路径、还是适不适合你？/);

  const noScope = Chat.buildDeepDiveTurn("初创核心工程师", "");
  assert.doesNotMatch(noScope.text, /口径/);

  const rendered = Chat.renderChatTurn(turn);
  assert.match(rendered, /chat-bubble--assistant/);
  assert.match(rendered, /想深挖「边缘 AI 部署」/);
});

test("chat.js takeDeepDiveCard：读取即清除（一次性握手），损坏数据返回 null", () => {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  try {
    assert.equal(Chat.takeDeepDiveCard(), null, "空 storage 返回 null");

    store.set(Chat.DEEP_DIVE_KEY, JSON.stringify({ title: "上海 vs 新一线", scope: "field" }));
    const card = Chat.takeDeepDiveCard();
    assert.deepEqual(card, { title: "上海 vs 新一线", scope: "field" });
    assert.equal(store.has(Chat.DEEP_DIVE_KEY), false, "读取后清除，第二次不再触发");

    store.set(Chat.DEEP_DIVE_KEY, "{broken json");
    assert.equal(Chat.takeDeepDiveCard(), null, "损坏 JSON 安全返回 null");

    store.set(Chat.DEEP_DIVE_KEY, JSON.stringify({ scope: "track" }));
    assert.equal(Chat.takeDeepDiveCard(), null, "缺 title 视为无效");
  } finally {
    delete globalThis.localStorage;
  }
});
