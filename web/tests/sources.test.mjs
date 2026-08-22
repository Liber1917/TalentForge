/* =========================================================
   sources.js 渲染断言（node:test + vm，无第三方依赖）
   在 Node 中加载 web/js/views/sources.js（纯渲染函数），
   用 fixture 数据断言源卡结构 / 状态徽章映射 / 脱敏显示 /
   插件卡文案 / 状态反馈 / 离线占位 / 转义 / 防御性。
   运行：node --test web/tests/sources.test.mjs
   ========================================================= */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

globalThis.window = globalThis;
const src = readFileSync(new URL("../js/views/sources.js", import.meta.url), "utf8");
vm.runInThisContext(src);
const Sources = globalThis.TalentForgeSources;

const FIXTURE_SOURCES = [
  {
    key: "boss",
    name: "Boss 直聘",
    kind: "cookie",
    home: "https://www.zhipin.com/",
    status: { source: "saved", masked: "wt2=****9876" },
    note: "粘贴浏览器复制的 cookie 串；留空保存不覆盖现有值；env TALENTFORGE_BOSS_COOKIE 优先于页面保存",
  },
  {
    key: "bilibili",
    name: "B站",
    kind: "extension",
    home: "https://www.bilibili.com/",
    status: { source: "extension", masked: "" },
    note: "由浏览器插件登录态采集，无需配置 cookie",
  },
  {
    key: "zhihu",
    name: "知乎",
    kind: "extension",
    home: "https://www.zhihu.com/",
    status: { source: "extension", masked: "" },
    note: "由浏览器插件登录态采集，无需配置 cookie",
  },
  {
    key: "github",
    name: "GitHub",
    kind: "public",
    home: "https://github.com/",
    status: { source: "public", masked: "" },
    note: "公开 API 可用；M4 作品源接入时可选配 token 提限额（预留）",
  },
];

/* ---------- Boss cookie 卡 ---------- */

test("renderSourceCard Boss 卡含粘贴框/保存/测试连接/状态行与脱敏摘要", () => {
  const html = Sources.renderSourceCard(FIXTURE_SOURCES[0]);
  assert.match(html, /data-source-key="boss"/);
  assert.match(html, /Boss 直聘/);
  assert.match(html, /需 cookie/);
  assert.match(html, />已保存</);
  assert.match(html, /wt2=\*\*\*\*9876/);
  assert.match(html, /当前凭据（脱敏）/);
  assert.match(html, /<textarea[^>]*data-role="source-input"/);
  assert.match(html, /留空保存不覆盖现有值/);
  assert.match(html, /data-action="source-save"/);
  assert.match(html, />保存</);
  assert.match(html, /data-action="source-verify"/);
  assert.match(html, />测试连接</);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /data-role="source-status"/);
  assert.match(html, /env TALENTFORGE_BOSS_COOKIE 优先于页面保存/);
});

test("renderSourceCard 未配置态显示占位提示而非空掩码", () => {
  const html = Sources.renderSourceCard({ ...FIXTURE_SOURCES[0], status: { source: "none", masked: "" } });
  assert.match(html, /尚未配置凭据/);
  assert.doesNotMatch(html, /当前凭据（脱敏）/);
  assert.doesNotMatch(html, /<code>[^<]/, "未配置不应渲染掩码 code");
});

test("状态徽章映射：none=琥珀、已配置=ok、插件/公开=中性", () => {
  const pill = (source) => Sources.pillClassForSource(source);
  assert.equal(pill("none"), "status-pill status-pill--trial");
  assert.equal(pill("env"), "status-pill status-pill--active");
  assert.equal(pill("saved"), "status-pill status-pill--active");
  assert.equal(pill("jobclaw"), "status-pill status-pill--active");
  assert.equal(pill("extension"), "status-pill status-pill--archived");
  assert.equal(pill("public"), "status-pill status-pill--archived");

  const none = Sources.renderSourceCard({ ...FIXTURE_SOURCES[0], status: { source: "none", masked: "" } });
  assert.match(none, /status-pill--trial/);
  assert.match(none, />未配置</);

  const env = Sources.renderSourceCard({ ...FIXTURE_SOURCES[0], status: { source: "env", masked: "wt2=****e123" } });
  assert.match(env, /status-pill--active/);
  assert.match(env, />环境变量</);

  const claw = Sources.renderSourceCard({ ...FIXTURE_SOURCES[0], status: { source: "jobclaw", masked: "wt2=****wxyz" } });
  assert.match(claw, />jobclaw 文件</);
});

/* ---------- 插件卡 / 公开卡 ---------- */

test("renderSourceCard B站/知乎插件卡：无需配置说明 + 无粘贴框", () => {
  for (const card of [FIXTURE_SOURCES[1], FIXTURE_SOURCES[2]]) {
    const html = Sources.renderSourceCard(card);
    assert.match(html, /插件取数/);
    assert.match(html, />插件采集</);
    assert.match(html, /由浏览器插件登录态采集，无需配置 cookie/);
    assert.doesNotMatch(html, /<textarea/);
    assert.doesNotMatch(html, /data-action="source-save"/);
    assert.doesNotMatch(html, /当前凭据/);
  }
});

test("renderSourceCard GitHub 公开卡：公开接口 + M4 预留说明", () => {
  const html = Sources.renderSourceCard(FIXTURE_SOURCES[3]);
  assert.match(html, /GitHub/);
  assert.match(html, />公开接口</);
  assert.match(html, /公开 API 可用/);
  assert.match(html, /M4 作品源接入时可选配 token/);
  assert.doesNotMatch(html, /<textarea/);
});

/* ---------- 列表 / 离线 ---------- */

test("renderSourcesList 渲染全部源卡；offline 输出后端未启动占位", () => {
  const html = Sources.renderSourcesList(FIXTURE_SOURCES, false);
  assert.equal((html.match(/data-source-key=/g) || []).length, 4);
  assert.match(html, /Boss 直聘/);
  assert.match(html, /知乎/);

  const offline = Sources.renderSourcesList(FIXTURE_SOURCES, true);
  assert.match(offline, /后端未启动/);
  assert.doesNotMatch(offline, /data-source-key=/);
  assert.match(Sources.renderOffline(), /role="status"/);
});

test("renderSourcesList 空数据/脏数据不抛错且无 undefined 字样", () => {
  const empty = Sources.renderSourcesList([], false);
  assert.equal(empty, "");
  const dirty = Sources.renderSourcesList([null, {}, { key: "boss" }], false);
  assert.equal(dirty.includes("undefined"), false);
  assert.equal(Sources.renderSourceCard(null), "");
});

/* ---------- 状态反馈 ---------- */

test("renderStatusFeedback 保存/验证结果徽章语义", () => {
  assert.match(Sources.renderStatusFeedback("saved"), />已保存</);
  assert.match(Sources.renderStatusFeedback("saved"), /status-pill--active/);
  assert.match(Sources.renderStatusFeedback("verify-ok"), />连接正常</);
  assert.match(Sources.renderStatusFeedback("verify-invalid"), />cookie 已失效，请重新粘贴</);
  assert.match(Sources.renderStatusFeedback("verify-invalid"), /status-pill--risk/);
  assert.match(Sources.renderStatusFeedback("error", "网络错误：超时"), /网络错误：超时/);
  assert.match(Sources.renderStatusFeedback("error", "x".repeat(100)), /…/);
  assert.equal(Sources.renderStatusFeedback("unknown"), "");
});

/* ---------- XSS / 工具 ---------- */

test("XSS：cookie 摘要/名称/说明含脚本一律转义", () => {
  const evil = Sources.renderSourceCard({
    key: "boss",
    name: '<script>alert(1)</script>',
    kind: "cookie",
    status: { source: "saved", masked: '<img src=x onerror=alert(2)>' },
    note: '<b>加粗注入</b>',
  });
  assert.match(evil, /&lt;script&gt;/);
  assert.doesNotMatch(evil, /<script>/);
  assert.match(evil, /&lt;img/);
  assert.doesNotMatch(evil, /<img src=x/);
  assert.doesNotMatch(evil, /<b>加粗注入<\/b>/);

  const feedback = Sources.renderStatusFeedback("error", '<script>alert(3)</script>');
  assert.match(feedback, /&lt;script&gt;/);
  assert.doesNotMatch(feedback, /<script>/);
});

test("esc / clip 工具行为正确", () => {
  assert.equal(Sources.esc(`<a href="x">&`), "&lt;a href=&quot;x&quot;&gt;&amp;");
  assert.equal(Sources.clip("abcdef", 3), "abc…");
  assert.equal(Sources.clip("abc", 10), "abc");
  assert.equal(Sources.clip(null), "");
});

/* ---------- partial 骨架 ---------- */

test("partials/sources.html 与 FALLBACK_PARTIAL 含头部 + 列表容器骨架", () => {
  const partial = readFileSync(new URL("../partials/sources.html", import.meta.url), "utf8");
  for (const doc of [partial, Sources.FALLBACK_PARTIAL]) {
    assert.match(doc, /sources-layout/);
    assert.match(doc, /id="sources-list"/);
    assert.match(doc, /role="list"/);
    assert.match(doc, /aria-label="平台源列表"/);
    assert.match(doc, /平台源/);
  }
});

/* ---------- 官网外链 ---------- */

test("renderSourceCard 卡面含平台官网外链（新窗口 + noopener）", () => {
  const boss = Sources.renderSourceCard(FIXTURE_SOURCES[0]);
  assert.match(boss, /<a class="source-card__site" href="https:\/\/www\.zhipin\.com\/" target="_blank" rel="noopener noreferrer"/);
  assert.match(boss, /官网 ↗/);
  for (const src of FIXTURE_SOURCES) {
    const html = Sources.renderSourceCard(src);
    assert.match(html, /class="source-card__site"/, `${src.key} 卡应含官网链接`);
  }
});

test("renderSourceCard 无 home 字段时不渲染官网链接；home 注入被转义", () => {
  const noHome = Sources.renderSourceCard({ key: "x", name: "X", kind: "public", status: { source: "public", masked: "" } });
  assert.doesNotMatch(noHome, /source-card__site/);
  const evil = Sources.renderSourceCard({
    key: "x", name: "X", kind: "public",
    home: '" onmouseover="alert(1)',
    status: { source: "public", masked: "" },
  });
  assert.doesNotMatch(evil, /" onmouseover=/, "未转义引号不得逃出 href 属性");
  assert.match(evil, /&quot;/, "注入的引号应被转义为实体");
});
