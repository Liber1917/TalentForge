/* =========================================================
   llm.js 渲染断言（node:test + vm，无第三方依赖）
   覆盖：FALLBACK_PARTIAL 骨架、renderStatusFeedback、
   renderOffline、esc/clip 转义。
   运行：node --test web/tests/llm.test.mjs
   ========================================================= */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const code = readFileSync(new URL("../js/views/llm.js", import.meta.url), "utf-8");
const sandbox = {
  window: {},
  document: undefined,
  fetch: undefined,
  console,
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const Llm = sandbox.window.TalentForgeLlm;

test("llm.js 模块暴露渲染函数", () => {
  assert.equal(typeof Llm.renderStatusFeedback, "function");
  assert.equal(typeof Llm.renderOffline, "function");
  assert.equal(typeof Llm.esc, "function");
  assert.equal(typeof Llm.clip, "function");
});

test("FALLBACK_PARTIAL 含 base_url/model/key/并发输入 + 保存/测试连接 + 状态行", () => {
  const html = Llm.FALLBACK_PARTIAL;
  assert.match(html, /模型服务/);
  assert.match(html, /data-role="llm-base-url"/);
  assert.match(html, /placeholder="https:\/\/api\.openai\.com\/v1"/);
  assert.match(html, /data-role="llm-model"/);
  assert.match(html, /data-role="llm-api-key"/);
  assert.match(html, /type="password"/);
  assert.match(html, /留空保存不覆盖现有值/);
  assert.match(html, /data-role="llm-concurrency"/);
  assert.match(html, /data-action="llm-save"/);
  assert.match(html, /data-action="llm-verify"/);
  assert.match(html, />保存</);
  assert.match(html, />测试连接</);
  assert.match(html, /data-role="llm-status"/);
  assert.match(html, /aria-live="polite"/);
  assert.doesNotMatch(html, /官网/, "独立页不应有官网链接");
});

test("renderStatusFeedback：已保存 / 连接正常（含延迟）/ 错误（risk）", () => {
  const saved = Llm.renderStatusFeedback("saved");
  assert.match(saved, /status-pill--active/);
  assert.match(saved, />已保存</);
  assert.match(saved, /去工作台生成报告/);

  const ok = Llm.renderStatusFeedback("verify-ok", { latency_ms: 1067 });
  assert.match(ok, /status-pill--active/);
  assert.match(ok, />连接正常（1067ms）</);

  const err = Llm.renderStatusFeedback("error", "连接失败：boom");
  assert.match(err, /status-pill--risk/);
  assert.match(err, />连接失败：boom</);
});

test("renderOffline 显示后端未启动占位", () => {
  const html = Llm.renderOffline();
  assert.match(html, /source-offline/);
  assert.match(html, /后端未启动/);
  assert.match(html, /127\.0\.0\.1:8420/);
});

test("XSS：状态详情含脚本一律转义", () => {
  const evil = Llm.renderStatusFeedback("error", '<script>alert(1)</script>');
  assert.match(evil, /&lt;script&gt;/);
  assert.doesNotMatch(evil, /<script>/);
});

test("clip 截断超长文本", () => {
  assert.equal(Llm.clip("a".repeat(100), 10), `${"a".repeat(10)}…`);
  assert.equal(Llm.clip("短文本", 10), "短文本");
});
