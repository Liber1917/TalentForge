/* =========================================================
   chat.js 渲染断言（node:test + vm，无第三方依赖）
   在 Node 中加载 web/js/views/chat.js（纯渲染函数），
   用 fixture 数据断言关键 class / 文案 / 转义 / 省略号。
   运行：node --test web/tests/chat.test.mjs
   ========================================================= */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

globalThis.window = globalThis;
const src = readFileSync(new URL("../js/views/chat.js", import.meta.url), "utf8");
vm.runInThisContext(src);
const Chat = globalThis.TalentForgeChat;

const DECISION = {
  type: "decision",
  job: {
    title: "Python 后端工程师",
    company: "星辰科技",
    url: "https://example.com/python_1001.html",
    salary: "25-50K·16薪",
  },
  verdict: "hold",
  reason: "市场契合高，但 JD 明确标注 996，与硬边界冲突。",
  risk_hits: [{ key: "996", label: "996 工作制" }],
  reflective_question: "",
  evidence: [
    { kind: "jd", ref: "python_1001.html", text: "工作时间为 996 工作制" },
    { kind: "dialogue", ref: "turn-1", text: "用户偏好深圳后端岗" },
  ],
};

const CLAIM = {
  type: "claim",
  claim_id: "claim-demo-01",
  text: "用户对分布式系统有深度积累",
  state: "trial",
  evidence_count: 0,
  sources: [{ kind: "dialogue", ref: "turn-3", at: "2026-08-21T09:03:00+00:00" }],
  confidence: 0.75,
};

const RISK = {
  type: "risk",
  key: "996",
  label: "996 工作制",
  why: "996 意味着劳动时间被系统性延长。",
};

const REFLECTIVE = { type: "reflective", question: "你上次说 996 是硬边界，怎么权衡？" };

test("renderDecisionCard 输出关键类与文案", () => {
  const html = Chat.renderDecisionCard(DECISION);
  assert.match(html, /verdict-badge--hold/);
  assert.match(html, />观望</);
  assert.match(html, /Python 后端工程师/);
  assert.match(html, /星辰科技/);
  assert.match(html, /25-50K·16薪/);
  assert.match(html, /996 工作制/);
  assert.match(html, /card--clickable/);
  assert.match(html, /data-js="decision"/);
  assert.match(html, /data-job-url="https:\/\/example\.com\/python_1001\.html"/);
  assert.match(html, /理由链 · 2 条/);
  assert.match(html, /evidence-item__kind/);
});

test("renderClaimCard trial 态含状态徽章与操作", () => {
  const html = Chat.renderClaimCard(CLAIM);
  assert.match(html, /status-pill--trial/);
  assert.match(html, />待验证</);
  assert.match(html, /置信 75%/);
  assert.match(html, /证据 0/);
  assert.match(html, /data-action="claim-confirm"/);
  assert.match(html, /data-action="claim-reject"/);
  assert.match(html, /用户对分布式系统有深度积累/);
  assert.match(html, /\d{2}-\d{2} \d{2}:\d{2}/);
});

test("renderClaimCard active 态隐藏操作按钮", () => {
  const html = Chat.renderClaimCard({ ...CLAIM, state: "active", evidence_count: 1 });
  assert.match(html, /status-pill--active/);
  assert.match(html, />已确认</);
  assert.doesNotMatch(html, /data-action="claim-confirm"/);
  assert.doesNotMatch(html, /data-action="claim-reject"/);
});

test("renderRiskNote 输出风险标签与 why", () => {
  const html = Chat.renderRiskNote(RISK);
  assert.match(html, /risk-note/);
  assert.match(html, /996 工作制/);
  assert.match(html, /为什么是风险/);
  assert.match(html, /劳动时间被系统性延长/);
});

test("renderReflectivePrompt 含提问与输入区", () => {
  const html = Chat.renderReflectivePrompt(REFLECTIVE);
  assert.match(html, /reflective-prompt/);
  assert.match(html, /怎么权衡/);
  assert.match(html, /reflective-prompt__input/);
  assert.match(html, /data-action="reflective-submit"/);
});

test("renderChatTurn user 右对齐 / assistant 含卡片即消息", () => {
  const user = Chat.renderChatTurn({ role: "user", text: "帮我看看岗位", cards: [], at: "" });
  assert.match(user, /chat-bubble--user/);
  assert.doesNotMatch(user, /chat-bubble--cards/);

  const assistant = Chat.renderChatTurn({
    role: "assistant",
    text: "给你看了两份",
    cards: [DECISION, RISK],
    at: "",
  });
  assert.match(assistant, /chat-bubble--assistant chat-bubble--cards/);
  assert.match(assistant, /chat-bubble__lead/);
  assert.match(assistant, /verdict-badge--hold/);
  assert.match(assistant, /risk-note/);

  const plain = Chat.renderChatTurn({ role: "assistant", text: "你好", cards: [], at: "" });
  assert.match(plain, /chat-bubble--assistant/);
  assert.doesNotMatch(plain, /chat-bubble--cards/);
});

test("XSS：文本一律转义，不出现原始脚本/事件属性", () => {
  const evilUser = Chat.renderChatTurn({
    role: "user",
    text: '<script>alert(1)</script><img src=x onerror=alert(2)>',
    cards: [],
    at: "",
  });
  assert.match(evilUser, /&lt;script&gt;/);
  assert.doesNotMatch(evilUser, /<script>/);
  assert.doesNotMatch(evilUser, /<img/);

  const evilCard = Chat.renderDecisionCard({
    ...DECISION,
    job: { ...DECISION.job, title: '<img src=x onerror="alert(1)">' },
    reason: '"><script>steal()</script>',
  });
  assert.match(evilCard, /&lt;img/);
  assert.doesNotMatch(evilCard, /<img src=x/);
  assert.doesNotMatch(evilCard, /<script>/);
});

test("EvidenceChain：decision 摘录省略 / claim 来源时间", () => {
  const decision = Chat.renderEvidenceChain(DECISION.evidence, { label: "理由链 · 2 条" });
  assert.match(decision, /evidence-item__text/);
  assert.match(decision, /工作时间为 996 工作制/);
  assert.match(decision, /理由链 · 2 条/);

  const claim = Chat.renderEvidenceChain(CLAIM.sources, { label: "证据链 · 1 条" });
  assert.match(claim, /evidence-item__at/);
  assert.match(claim, /\d{2}-\d{2} \d{2}:\d{2}/);
});

test("renderCard 按 type 分发四种卡片", () => {
  assert.match(Chat.renderCard(DECISION), /decision-card/);
  assert.match(Chat.renderCard(CLAIM), /claim-card/);
  assert.match(Chat.renderCard(RISK), /risk-note/);
  assert.match(Chat.renderCard(REFLECTIVE), /reflective-prompt/);
  assert.equal(Chat.renderCard({ type: "unknown" }), "");
});

test("mockAssistantReply 产出含用户片段的 ReflectivePrompt（fixtures 风格）", () => {
  const reply = Chat.mockAssistantReply("我想看看深圳的岗位");
  assert.equal(reply.role, "assistant");
  assert.equal(reply.cards[0].type, "reflective");
  assert.match(reply.cards[0].question, /我想看看深圳的岗位/);
  assert.match(reply.cards[0].question, /优先级有多高/);
});

test("countTrialClaims 只统计 trial 态主张", () => {
  const turns = [
    { role: "assistant", cards: [{ type: "claim", claim_id: "a", state: "trial" }] },
    { role: "assistant", cards: [{ type: "claim", claim_id: "b", state: "active" }] },
    { role: "assistant", cards: [{ type: "claim", claim_id: "c", state: "trial" }] },
  ];
  assert.equal(Chat.countTrialClaims(turns), 2);
  assert.equal(Chat.countTrialClaims([]), 0);
});

test("clip 截断超长文本并加省略号；esc 转义特殊字符", () => {
  assert.equal(Chat.clip("abc", 2), "ab…");
  assert.equal(Chat.clip("abc", 10), "abc");
  assert.equal(Chat.esc(`<a href="x">&`), "&lt;a href=&quot;x&quot;&gt;&amp;");
});

test("本地假数据聊天流含 5 轮与全部四种卡片类型", () => {
  const turns = Chat.LOCAL_FIXTURE_CHAT;
  assert.equal(turns.length, 5);
  assert.equal(turns[0].role, "user");
  assert.equal(turns[1].cards.length, 2);
  const types = new Set();
  for (const t of turns) {
    for (const c of t.cards || []) types.add(c.type);
  }
  assert.deepEqual([...types].sort(), ["claim", "decision", "reflective", "risk"]);
  assert.equal(Chat.countTrialClaims(turns), 1);
});

test("partials/chat.html 含聊天流与 composer 骨架（aria-live / aria-label）", () => {
  const partial = readFileSync(new URL("../partials/chat.html", import.meta.url), "utf8");
  assert.match(partial, /id="chat-stream"/);
  assert.match(partial, /role="log"/);
  assert.match(partial, /aria-live="polite"/);
  assert.match(partial, /id="chat-composer"/);
  assert.match(partial, /id="chat-input"/);
  assert.match(partial, /aria-label="对话输入框"/);
  assert.match(partial, /id="chat-send"/);
  assert.match(partial, /id="chat-thinking"/);
});
