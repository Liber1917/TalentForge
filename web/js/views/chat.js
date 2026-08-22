/* =========================================================
   TalentForge 对话首页视图（#chat）
   - 渲染聊天流：ChatBubble（user 右对齐 / assistant 左对齐；
     assistant 含卡片时卡片即消息，无气泡边框）
   - 四类卡片渲染：DecisionCard / ClaimCard / RiskNote / ReflectivePrompt
   - EvidenceChain 用 <details>/<summary> 展开收起（锚点行：
     证据类型 + 来源 + 时间 + 原文摘录，摘录单行省略号）
   - 卡片操作：claim 确认/驳回（假数据模式本地 mock 局部更新；
     真模式调端点）；DecisionCard 整体可点击 → 跳工作台并定位岗位
   - Composer：发送 → 假数据模式本地 mock 回复；真模式 POST /api/chat/turns
   - ReflectivePrompt 内嵌输入框：回答 → mock 追加对话 + 局部更新
   渲染函数为纯字符串输出（文本一律 esc 转义，杜绝 innerHTML 拼接
   用户/LLM 文本），DOM 层通过 <template> 解析后挂载，便于 node:test 直接断言。
   ========================================================= */

"use strict";

const TalentForgeChat = (() => {
  /* ---------- 标签映射（DESIGN.md §2 三值语义 / §5 状态） ---------- */
  const VERDICT_LABEL = { apply: "投", hold: "观望", skip: "不投" };
  const STATE_LABEL = { trial: "待验证", active: "已确认", archived: "已归档" };
  const KIND_LABEL = {
    jd: "JD 原文",
    resume: "简历",
    dialogue: "对话",
    feedback: "反馈",
    behavior: "行为",
    system: "系统",
  };

  /* ---------- 离线假数据：镜像 talentforge/api/fixtures.py get_fixture_chat ---------- */
  const LOCAL_FIXTURE_CHAT = [
    {
      role: "user",
      text: "帮我看看深圳的后端岗位？最近在找机会，想听听你的判断。",
      cards: [],
      at: "2026-08-21T09:00:00+00:00",
    },
    {
      role: "assistant",
      text: "给你看了两份深圳后端岗，先各给一个结论：一家先观望，一家直接排除。",
      cards: [
        {
          type: "decision",
          job: {
            title: "Python 后端工程师",
            company: "星辰科技",
            url: "https://www.zhipin.com/job_detail/python_1001.html",
            salary: "25-50K·16薪",
          },
          verdict: "hold",
          reason:
            "市场契合高，但 JD 明确标注 996，与你上次划的硬边界冲突——先观望，看能否谈到工时与对价。",
          risk_hits: [{ key: "996", label: "996 工作制" }],
          reflective_question: "",
          evidence: [
            { kind: "jd", ref: "python_1001.html", text: "工作时间为 996 工作制" },
            { kind: "dialogue", ref: "turn-1", text: "用户偏好深圳后端岗" },
          ],
        },
        {
          type: "decision",
          job: {
            title: "高级后端开发（Java）",
            company: "云帆信息",
            url: "https://www.zhipin.com/job_detail/java_1002.html",
            salary: "15-25K",
          },
          verdict: "skip",
          reason: "薪资低于你的保留工资，且含竞业限制条款，与硬边界直接冲突。",
          risk_hits: [{ key: "竞业限制", label: "竞业限制条款" }],
          reflective_question: "",
          evidence: [
            { kind: "jd", ref: "java_1002.html", text: "含竞业限制条款，范围覆盖同业" },
            { kind: "system", ref: "deal-breaker", text: "用户 deal_breakers 含竞业限制" },
          ],
        },
      ],
      at: "2026-08-21T09:01:00+00:00",
    },
    {
      role: "user",
      text: "星辰科技标着 996，云帆还有竞业，我都挺犹豫。其实我在分布式系统这块积累挺深，最近在准备系统设计面试。",
      cards: [],
      at: "2026-08-21T09:02:00+00:00",
    },
    {
      role: "assistant",
      text: "你的犹豫有依据，风险先单独拆开讲；另外把“系统设计积累”记成一条待验证主张，后续用行为验证。",
      cards: [
        {
          type: "risk",
          key: "996",
          label: "996 工作制",
          why: "996 意味着劳动时间被系统性延长——超出法定工时的部分通常不支付对价，长期会压缩你的再生产时间（睡眠/学习/社交）。这不是道德判断，是你需要知情权衡的事实。",
        },
        {
          type: "claim",
          claim_id: "claim-demo-sysdes-01",
          text: "用户对分布式系统/系统设计有深度积累，正在系统化准备系统设计面试",
          state: "trial",
          evidence_count: 0,
          sources: [{ kind: "dialogue", ref: "turn-3", at: "2026-08-21T09:03:00+00:00" }],
          confidence: 0.75,
        },
        {
          type: "reflective",
          question: "你上次说 996 是硬边界，现在这份岗位明确标着 996——怎么权衡？",
        },
      ],
      at: "2026-08-21T09:03:00+00:00",
    },
    {
      role: "user",
      text: "嗯，996 如果给足对价和时间弹性我可以谈，但竞业限制是硬边界。",
      cards: [],
      at: "2026-08-21T09:04:00+00:00",
    },
  ];

  /* 兜底骨架：与 web/partials/chat.html 保持一致（fetch 失败时注入） */
  const FALLBACK_PARTIAL = `
<div class="chat-layout">
  <div class="chat-stream" id="chat-stream" role="log" aria-live="polite" aria-relevant="additions" aria-label="对话流"></div>
  <div class="chat-composer">
    <form class="composer" id="chat-composer" novalidate>
      <input class="input" id="chat-input" type="text" placeholder="想聊什么、想问什么、想投什么…" aria-label="对话输入框" autocomplete="off" />
      <button class="btn btn--primary" id="chat-send" type="submit">发送</button>
    </form>
  </div>
  <p class="chat-thinking" id="chat-thinking" hidden>正在思考…</p>
</div>`;

  /* ---------- 视图状态 ---------- */
  const state = {
    loaded: false,
    turns: [],
    sending: false,
  };

  /* ---------- 工具 ---------- */
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
    ));
  }

  function clip(value, n = 40) {
    const s = String(value ?? "").replace(/\s+/g, " ").trim();
    return s.length > n ? `${s.slice(0, n)}…` : s;
  }

  function fmtAt(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    const pad = (x) => String(x).padStart(2, "0");
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function htmlToElement(html) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html.trim();
    return tpl.content.firstElementChild;
  }

  /* ---------- 纯渲染函数（测试可直接断言） ---------- */

  function renderEvidenceChain(items, { label } = {}) {
    const list = Array.isArray(items) ? items : [];
    const summary = label || `证据链 · ${list.length} 条`;
    const rows = list.map((item) => {
      const kind = KIND_LABEL[item.kind] || item.kind || "";
      const excerpt = item.text ? clip(item.text, 48) : "";
      const at = item.at ? fmtAt(item.at) : "";
      return `
            <li class="evidence-item">
              <span class="evidence-item__anchor">
                <span class="evidence-item__kind">${esc(kind)}</span>
                <span class="evidence-item__ref">${esc(item.ref)}</span>
                ${at ? `<span class="evidence-item__at">${esc(at)}</span>` : ""}
              </span>
              ${excerpt ? `<span class="evidence-item__text" title="${esc(item.text)}">${esc(excerpt)}</span>` : ""}
            </li>`;
    });
    return `
        <details class="evidence-chain">
          <summary class="evidence-chain__summary">${esc(summary)}</summary>
          <ol class="evidence-chain__list">
            ${rows.join("")}
          </ol>
        </details>`;
  }

  function renderDecisionCard(card) {
    const job = card.job || {};
    const riskHits = Array.isArray(card.risk_hits) ? card.risk_hits : [];
    const evidence = Array.isArray(card.evidence) ? card.evidence : [];
    const verdict = VERDICT_LABEL[card.verdict] || card.verdict;
    const metaBits = [
      riskHits.length ? `风险 ${riskHits.length} 项` : "",
      evidence.length ? `证据 ${evidence.length} 条` : "",
    ].filter(Boolean);
    const riskTags = riskHits.length
      ? `<div class="risk-tags">${riskHits
          .map((r) => `<span class="risk-tag">风险 · ${esc(r.label)}</span>`)
          .join("")}</div>`
      : "";
    const reflective = card.reflective_question
      ? renderReflectivePrompt({ type: "reflective", question: card.reflective_question })
      : "";
    return `
        <article class="card card--embedded card--clickable decision-card"
                 data-js="decision" data-job-url="${esc(job.url || "")}" tabindex="0"
                 role="button" aria-label="查看岗位：${esc(job.title || "")}（${esc(verdict)}）">
          <header class="claim-card__head">
            <span class="verdict-badge verdict-badge--${esc(card.verdict)}">${esc(verdict)}</span>
            ${metaBits.length ? `<span class="claim-card__meta">${esc(metaBits.join(" · "))}</span>` : ""}
          </header>
          <h3 class="card__title">${esc(job.title)}</h3>
          <p class="card__meta">${esc([job.company, job.salary].filter(Boolean).join(" · "))}</p>
          <p class="card__body">${esc(card.reason)}</p>
          ${riskTags}
          ${renderEvidenceChain(evidence, { label: `理由链 · ${evidence.length} 条` })}
          ${reflective}
        </article>`;
  }

  function renderClaimCard(card) {
    const sources = Array.isArray(card.sources) ? card.sources : [];
    const stateName = STATE_LABEL[card.state] || card.state;
    const confidence = Math.round((Number(card.confidence) || 0) * 100);
    const actions =
      card.state === "trial"
        ? `
          <footer class="claim-card__actions">
            <button class="btn btn--primary btn--sm" type="button" data-action="claim-confirm"
                    aria-label="确认主张：${esc(clip(card.text, 20))}">确认</button>
            <button class="btn btn--ghost btn--sm" type="button" data-action="claim-reject"
                    aria-label="驳回主张：${esc(clip(card.text, 20))}">驳回</button>
          </footer>`
        : "";
    return `
        <article class="card card--embedded claim-card"
                 data-claim-id="${esc(card.claim_id)}" data-state="${esc(card.state)}">
          <header class="claim-card__head">
            <span class="status-pill status-pill--${esc(card.state)}">${esc(stateName)}</span>
            <span class="claim-card__meta">置信 ${confidence}% · 证据 ${Number(card.evidence_count) || 0}</span>
          </header>
          <p class="claim-card__text">${esc(card.text)}</p>
          ${renderEvidenceChain(sources, { label: `证据链 · ${sources.length} 条` })}
          ${actions}
        </article>`;
  }

  function renderRiskNote(card) {
    return `
        <aside class="risk-note">
          <div class="risk-note__label">风险 · ${esc(card.label)}</div>
          <details>
            <summary class="risk-note__summary">为什么是风险</summary>
            <p class="risk-note__why">${esc(card.why)}</p>
          </details>
        </aside>`;
  }

  function renderReflectivePrompt(card) {
    return `
        <div class="reflective-prompt" data-js="reflective" data-answered="false">
          <p class="reflective-prompt__q">“${esc(card.question)}”</p>
          <div class="reflective-prompt__input">
            <input class="input" type="text" placeholder="写下你的权衡…"
                   aria-label="回答反思问题：${esc(clip(card.question, 20))}" />
            <button class="btn btn--primary btn--sm" type="button" data-action="reflective-submit">回答</button>
          </div>
        </div>`;
  }

  function renderCard(card) {
    switch (card && card.type) {
      case "decision":
        return renderDecisionCard(card);
      case "claim":
        return renderClaimCard(card);
      case "risk":
        return renderRiskNote(card);
      case "reflective":
        return renderReflectivePrompt(card);
      default:
        return "";
    }
  }

  /* 视图提及 → hash 跳转链接：助手文案里 『平台源』 等提及变可点击（输入必须已 esc） */
  const VIEW_LINKS = {
    平台源: "#/sources",
    工作台: "#/jobs",
    画像: "#/profile",
    对话: "#/chat",
  };

  function linkifyMentions(escapedHtml) {
    let out = String(escapedHtml || "");
    for (const [label, href] of Object.entries(VIEW_LINKS)) {
      out = out.replaceAll(
        `『${label}』`,
        `<a class="chat-view-link" href="${href}">『${label}』</a>`
      );
    }
    return out;
  }

  function renderChatTurn(turn) {
    const text = String(turn.text || "").trim();
    const cards = Array.isArray(turn.cards) ? turn.cards : [];
    if (turn.role === "user") {
      return `<div class="chat-bubble chat-bubble--user">${esc(text)}</div>`;
    }
    if (cards.length) {
      return `
        <div class="chat-bubble chat-bubble--assistant chat-bubble--cards">
          ${text ? `<p class="chat-bubble__lead">${linkifyMentions(esc(text))}</p>` : ""}
          ${cards.map(renderCard).join("")}
        </div>`;
    }
    return `<div class="chat-bubble chat-bubble--assistant">${linkifyMentions(esc(text))}</div>`;
  }

  /* ---------- 假数据模式 mock（风格取自 fixtures.py 反思提问） ---------- */
  function mockAssistantReply(text) {
    const snippet = clip(text, 24);
    return {
      role: "assistant",
      text: "我记下了。想先跟你确认一层：",
      cards: [
        { type: "reflective", question: `你刚说“${snippet}”——这件事对你接下来的求职决策，优先级有多高？` },
      ],
      at: new Date().toISOString(),
    };
  }

  /* ---------- DOM 挂载与交互 ---------- */
  function getStream() {
    return document.getElementById("chat-stream");
  }

  let partialPromise = null;
  function mountPartial() {
    if (partialPromise) return partialPromise;
    partialPromise = (async () => {
      const host = document.getElementById("chat");
      if (!host || host.querySelector(".chat-stream")) return;
      try {
        const res = await fetch("partials/chat.html");
        if (res.ok) {
          host.innerHTML = await res.text();
          wireEvents();
          return;
        }
      } catch (err) {
        /* 静默降级到内置兜底模板 */
      }
      host.innerHTML = FALLBACK_PARTIAL;
      wireEvents();
    })();
    return partialPromise;
  }

  async function loadChat() {
    if (state.loaded) return;
    const stream = getStream();
    if (!stream) return;
    state.loaded = true;

    if (TalentForgeApi.USE_FIXTURES) {
      state.turns = LOCAL_FIXTURE_CHAT;
      renderStream();
      updatePendingCount();
      return;
    }

    const loading = htmlToElement(
      '<div class="chat-bubble chat-bubble--assistant" aria-hidden="true">正在加载对话…</div>'
    );
    stream.appendChild(loading);
    try {
      const turns = await TalentForgeApi.getChat();
      state.turns = Array.isArray(turns) ? turns : [];
    } catch (err) {
      state.turns = [
        { role: "assistant", text: `对话加载失败：${err.message}`, cards: [], at: new Date().toISOString() },
      ];
    }
    stream.replaceChildren(...state.turns.map((t) => htmlToElement(renderChatTurn(t))));
    updatePendingCount();
  }

  function renderStream() {
    const stream = getStream();
    if (!stream) return;
    stream.replaceChildren(...state.turns.map((t) => htmlToElement(renderChatTurn(t))));
  }

  function appendTurn(turn) {
    const stream = getStream();
    if (!stream) return;
    state.turns.push(turn);
    const el = htmlToElement(renderChatTurn(turn));
    stream.appendChild(el);
    el.scrollIntoView({ block: "nearest" });
  }

  function setComposerBusy(busy) {
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("chat-send");
    const thinking = document.getElementById("chat-thinking");
    if (input) input.disabled = busy;
    if (sendBtn) sendBtn.disabled = busy;
    if (thinking) thinking.hidden = !busy;
  }

  async function sendMessage() {
    const input = document.getElementById("chat-input");
    if (!input) return;
    const text = input.value.trim();
    if (!text || state.sending) return;
    input.value = "";
    appendTurn({ role: "user", text, cards: [], at: new Date().toISOString() });

    state.sending = true;
    setComposerBusy(true);
    try {
      if (TalentForgeApi.USE_FIXTURES) {
        appendTurn(mockAssistantReply(text));
      } else {
        const res = await TalentForgeApi.postTurn({ text });
        const reply = Array.isArray(res) ? res : [res];
        reply.forEach((t) => appendTurn(normalizeTurn(t)));
      }
    } catch (err) {
      appendTurn({
        role: "assistant",
        text: `抱歉，我这边出了点状况：${err.message}`,
        cards: [],
        at: new Date().toISOString(),
      });
    } finally {
      state.sending = false;
      setComposerBusy(false);
    }
  }

  function normalizeTurn(t) {
    return {
      role: t && t.role === "user" ? "user" : "assistant",
      text: String((t && t.text) || ""),
      cards: Array.isArray(t && t.cards) ? t.cards : [],
      at: (t && t.at) || new Date().toISOString(),
    };
  }

  function countTrialClaims(turns) {
    let n = 0;
    for (const turn of turns || []) {
      for (const card of turn.cards || []) {
        if (card.type === "claim" && card.state === "trial") n += 1;
      }
    }
    return n;
  }

  function updatePendingCount() {
    const el = document.getElementById("pending-count");
    if (!el) return;
    el.textContent = `待定池 ${countTrialClaims(state.turns)}`;
  }

  function findClaimInState(claimId) {
    for (const turn of state.turns) {
      for (const card of turn.cards || []) {
        if (card.type === "claim" && card.claim_id === claimId) return card;
      }
    }
    return null;
  }

  async function actionClaim(cardEl, action) {
    const claimId = cardEl.dataset.claimId;
    const ok = action === "confirm";
    const nextState = ok ? "active" : "archived";
    const card = findClaimInState(claimId);
    if (card) {
      card.state = nextState;
      if (ok) card.evidence_count = (Number(card.evidence_count) || 0) + 1;
    }
    const merged = card || { type: "claim", claim_id: claimId, text: "", state: nextState };
    cardEl.outerHTML = renderClaimCard(merged);
    updatePendingCount();

    if (!TalentForgeApi.USE_FIXTURES) {
      try {
        if (ok) {
          await TalentForgeApi.confirmClaim(claimId);
        } else {
          await TalentForgeApi.rejectClaim(claimId);
        }
      } catch (err) {
        /* 真模式端点失败：本地已乐观更新，提示即可 */
      }
    }
  }

  function answerReflective(promptEl, answer) {
    const inputRow = promptEl.querySelector(".reflective-prompt__input");
    if (inputRow) {
      const note = document.createElement("p");
      note.className = "card__meta";
      note.textContent = "已记录你的回答，我会留意相关证据。";
      inputRow.replaceWith(note);
    }
    promptEl.setAttribute("data-answered", "true");
    appendTurn({ role: "user", text: answer, cards: [], at: new Date().toISOString() });
    if (TalentForgeApi.USE_FIXTURES) {
      appendTurn({
        role: "assistant",
        text: "这条我记进你的画像了，之后会留意相关证据。",
        cards: [],
        at: new Date().toISOString(),
      });
    } else {
      const question = promptEl.querySelector(".reflective-prompt__q")
        ? promptEl.querySelector(".reflective-prompt__q").textContent.replace(/^“|”$/g, "")
        : "";
      TalentForgeApi.postTurn({ text: answer, reply_to: question }).catch(() => {});
    }
  }

  function openJob(cardEl) {
    const url = cardEl.dataset.jobUrl || "";
    const titleEl = cardEl.querySelector(".card__title");
    const title = titleEl ? titleEl.textContent : "";
    window.dispatchEvent(new CustomEvent("job:focus", { detail: { url, title } }));
    if (window.TalentForgeRouter) {
      window.TalentForgeRouter.navigate("/jobs");
    }
  }

  function isInteractiveTarget(target) {
    return Boolean(target.closest("button, a, summary, input, textarea, select"));
  }

  function onStreamClick(evt) {
    const decisionEl = evt.target.closest("[data-js='decision']");
    const confirmBtn = evt.target.closest("[data-action='claim-confirm']");
    const rejectBtn = evt.target.closest("[data-action='claim-reject']");
    const reflectBtn = evt.target.closest("[data-action='reflective-submit']");

    if (reflectBtn) {
      evt.preventDefault();
      submitReflective(reflectBtn);
      return;
    }
    if (confirmBtn) {
      evt.preventDefault();
      actionClaim(confirmBtn.closest("[data-claim-id]"), "confirm");
      return;
    }
    if (rejectBtn) {
      evt.preventDefault();
      actionClaim(rejectBtn.closest("[data-claim-id]"), "reject");
      return;
    }
    if (decisionEl && !isInteractiveTarget(evt.target)) {
      evt.preventDefault();
      openJob(decisionEl);
    }
  }

  function onStreamKeydown(evt) {
    if (evt.key !== "Enter") return;
    const decisionEl = evt.target.closest("[data-js='decision']");
    const reflectiveInput = evt.target.matches("[data-js='reflective'] input");
    if (reflectiveInput) {
      evt.preventDefault();
      const promptEl = evt.target.closest("[data-js='reflective']");
      submitReflective(promptEl.querySelector("[data-action='reflective-submit']"));
      return;
    }
    if (decisionEl && !isInteractiveTarget(evt.target)) {
      evt.preventDefault();
      openJob(decisionEl);
    }
  }

  function submitReflective(btn) {
    if (!btn) return;
    const promptEl = btn.closest("[data-js='reflective']");
    const input = promptEl && promptEl.querySelector("input");
    const answer = input ? input.value.trim() : "";
    if (!answer) return;
    answerReflective(promptEl, answer);
  }

  function wireEvents() {
    const stream = getStream();
    if (stream) {
      stream.addEventListener("click", onStreamClick);
      stream.addEventListener("keydown", onStreamKeydown);
    }
    const form = document.getElementById("chat-composer");
    if (form) form.addEventListener("submit", (evt) => { evt.preventDefault(); sendMessage(); });
  }

  function onEnterChat() {
    mountPartial().then(loadChat);
  }

  function init() {
    if (window.TalentForgeRouter && typeof window.TalentForgeRouter.onView === "function") {
      window.TalentForgeRouter.onView("chat", onEnterChat);
    } else {
      window.addEventListener("route:change", (evt) => {
        if (evt.detail && evt.detail.view === "chat") onEnterChat();
      });
    }
    if (window.TalentForgeRouter && window.TalentForgeRouter.currentPath() === "/chat") {
      onEnterChat();
    }
  }

  return {
    LOCAL_FIXTURE_CHAT,
    VIEW_LINKS,
    clip,
    esc,
    fmtAt,
    linkifyMentions,
    countTrialClaims,
    mockAssistantReply,
    normalizeTurn,
    renderCard,
    renderChatTurn,
    renderClaimCard,
    renderDecisionCard,
    renderEvidenceChain,
    renderReflectivePrompt,
    renderRiskNote,
    init,
  };
})();

if (typeof window !== "undefined") {
  window.TalentForgeChat = TalentForgeChat;
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => TalentForgeChat.init());
  } else {
    TalentForgeChat.init();
  }
}
