/* =========================================================
   TalentForge 模型服务设置视图（#/llm，M8）
   - 独立页面（非平台源卡）：配置 OpenAI 兼容 LLM API——
     base_url / API Key / 模型 / 决策匹配并发度
   - 保存：POST /api/llm/settings（merge；API Key 留空不覆盖，
     掩码读回，永不回传明文）
   - 测试连接：POST /api/llm/settings/verify（提交配置临时外呼，
     显示延迟或错误，不落盘）
   - 进入视图时 GET /api/llm/settings 回填当前值 + 生效来源
   - 真功能直连后端（不走 USE_FIXTURES base，无假数据模式）
   渲染函数为纯字符串输出（文本一律 esc 转义），DOM 挂载分离，
   便于 node:test 直接断言。
   ========================================================= */

"use strict";

const TalentForgeLlm = (() => {
  /* 兜底骨架：与 web/partials/llm.html 保持一致（fetch 失败时注入） */
  const FALLBACK_PARTIAL = `
<div class="llm-layout">
  <header class="llm-head">
    <h2 class="llm-head__title">模型服务</h2>
    <p class="llm-head__hint">配置自定义 LLM API（OpenAI 兼容端点）——base_url / API Key / 模型 / 决策匹配并发度</p>
  </header>
  <form class="llm-form" id="llm-form" aria-label="模型服务配置">
    <label class="overline" for="llm-base-url">Base URL</label>
    <input class="input llm-input" id="llm-base-url" type="text"
           placeholder="https://api.openai.com/v1"
           autocomplete="off" spellcheck="false" data-role="llm-base-url">
    <label class="overline" for="llm-model">模型</label>
    <input class="input llm-input" id="llm-model" type="text"
           placeholder="gpt-4o-mini"
           autocomplete="off" spellcheck="false" data-role="llm-model">
    <label class="overline" for="llm-api-key">API Key</label>
    <input class="input llm-input" id="llm-api-key" type="password"
           placeholder="sk-…（留空保存不覆盖现有值）"
           autocomplete="off" spellcheck="false" data-role="llm-api-key">
    <label class="overline" for="llm-concurrency">决策匹配并发度</label>
    <input class="input llm-input" id="llm-concurrency" type="number" min="1" max="16"
           placeholder="5" data-role="llm-concurrency">
    <div class="llm-actions">
      <button class="btn btn--primary" type="button" data-action="llm-save">保存</button>
      <button class="btn btn--ghost" type="button" data-action="llm-verify">测试连接</button>
    </div>
    <p class="llm-status" role="status" aria-live="polite" data-role="llm-status"></p>
  </form>
</div>`;

  const OFFLINE_HINT = "后端未启动：请先运行 TalentForge 服务（127.0.0.1:8420），再回到此页配置模型服务";
  const VERIFY_RUNNING_TEXT = "测试中…";

  /* ---------- 视图状态 ---------- */
  const state = { loaded: false, offline: false };

  /* ---------- 工具 ---------- */
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
    ));
  }

  function clip(value, n = 60) {
    const s = String(value ?? "").replace(/\s+/g, " ").trim();
    return s.length > n ? `${s.slice(0, n)}…` : s;
  }

  /* ---------- 纯渲染函数（测试可直接断言） ---------- */

  /** 操作状态行：已保存 / 连接正常（ok）/ 错误（risk）。 */
  function renderStatusFeedback(kind, detail) {
    if (kind === "saved") {
      return `<span class="status-pill status-pill--active">已保存</span> <a class="source-next-link" href="#/jobs">去工作台生成报告 →</a>`;
    }
    if (kind === "verify-ok") {
      const ms = detail && detail.latency_ms != null ? `（${Number(detail.latency_ms)}ms）` : "";
      return `<span class="status-pill status-pill--active">连接正常${esc(ms)}</span>`;
    }
    if (kind === "error") {
      return `<span class="status-pill status-pill--risk">${esc(clip(detail || "操作失败，请稍后重试", 60))}</span>`;
    }
    return "";
  }

  /** 后端未启动占位。 */
  function renderOffline() {
    return `
        <div class="source-offline" role="status">
          <p>${esc(OFFLINE_HINT)}</p>
        </div>`;
  }

  /* ---------- DOM 挂载与交互 ---------- */
  function getHost() {
    return document.getElementById("llm");
  }

  let partialPromise = null;
  function mountPartial() {
    if (partialPromise) return partialPromise;
    partialPromise = (async () => {
      const host = getHost();
      if (!host || host.querySelector(".llm-layout")) return;
      try {
        const res = await fetch("partials/llm.html");
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

  async function requestJson(url, options) {
    const res = await fetch(url, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      cache: "no-store",
      ...options,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function getField(role) {
    const host = getHost();
    const el = host && host.querySelector(`[data-role='${role}']`);
    return el ? el.value : "";
  }

  function setStatusLine(html) {
    const host = getHost();
    const line = host && host.querySelector("[data-role='llm-status']");
    if (line) line.innerHTML = html;
  }

  /** 回填表单：GET /api/llm/settings 的掩码视图填入输入框（key 显示掩码占位，不填值）。 */
  function fillForm(settings, source) {
    if (!settings) return;
    const host = getHost();
    const base = host && host.querySelector("[data-role='llm-base-url']");
    const model = host && host.querySelector("[data-role='llm-model']");
    const key = host && host.querySelector("[data-role='llm-api-key']");
    const conc = host && host.querySelector("[data-role='llm-concurrency']");
    if (base && settings.base_url) base.value = settings.base_url;
    if (model && settings.model) model.value = settings.model;
    if (key && settings.api_key) key.placeholder = `已配置 ${settings.api_key}（留空不覆盖）`;
    if (conc && settings.match_concurrency) conc.value = settings.match_concurrency;
    if (source) setStatusLine(`当前生效来源：${esc(String(source))}`);
  }

  /** 懒加载当前设置回填（GET /api/llm/settings，含生效来源）。 */
  async function loadSettings() {
    try {
      const data = await requestJson("/api/llm/settings", { method: "GET" });
      state.offline = false;
      fillForm(data && data.settings, data && data.source);
    } catch (err) {
      state.offline = true;
      setStatusLine(renderStatusFeedback("error", "加载失败：后端未启动"));
    }
  }

  /** 保存：POST /api/llm/settings（merge，key 留空不覆盖）；成功后回填掩码视图。 */
  async function saveSettings() {
    const body = {
      base_url: getField("llm-base-url"),
      model: getField("llm-model"),
      match_concurrency: Number(getField("llm-concurrency")) || undefined,
    };
    const apiKey = getField("llm-api-key");
    if (apiKey.trim()) body.api_key = apiKey.trim();
    setStatusLine("");
    try {
      const data = await requestJson("/api/llm/settings", {
        method: "POST",
        body: JSON.stringify(body),
      });
      fillForm(data && data.settings);
      setStatusLine(renderStatusFeedback("saved"));
    } catch (err) {
      setStatusLine(renderStatusFeedback("error", "保存失败：后端未启动或不可写"));
    }
  }

  /** 测试连接：POST /api/llm/settings/verify（提交配置临时外呼，不落盘）。 */
  async function verifySettings(btn) {
    const body = {
      base_url: getField("llm-base-url"),
      model: getField("llm-model"),
    };
    const apiKey = getField("llm-api-key");
    if (apiKey.trim()) body.api_key = apiKey.trim();
    const original = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = VERIFY_RUNNING_TEXT;
    }
    setStatusLine("");
    try {
      const data = await requestJson("/api/llm/settings/verify", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (data && data.ok) {
        setStatusLine(renderStatusFeedback("verify-ok", data));
      } else {
        setStatusLine(renderStatusFeedback("error", (data && data.detail) || "连接失败"));
      }
    } catch (err) {
      setStatusLine(renderStatusFeedback("error", "测试失败：后端未启动"));
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = original || "测试连接";
      }
    }
  }

  function onHostClick(evt) {
    const saveBtn = evt.target.closest("[data-action='llm-save']");
    if (saveBtn) {
      evt.preventDefault();
      saveSettings();
      return;
    }
    const verifyBtn = evt.target.closest("[data-action='llm-verify']");
    if (verifyBtn) {
      evt.preventDefault();
      verifySettings(verifyBtn);
    }
  }

  function wireEvents() {
    const host = getHost();
    if (host) host.addEventListener("click", onHostClick);
  }

  function onEnterLlm() {
    mountPartial().then(() => {
      if (!state.loaded) {
        state.loaded = true;
        loadSettings();
      }
    });
  }

  function init() {
    if (window.TalentForgeRouter && typeof window.TalentForgeRouter.onView === "function") {
      window.TalentForgeRouter.onView("llm", onEnterLlm);
    } else {
      window.addEventListener("route:change", (evt) => {
        if (evt.detail && evt.detail.view === "llm") onEnterLlm();
      });
    }
    if (window.TalentForgeRouter && window.TalentForgeRouter.currentPath() === "/llm") {
      onEnterLlm();
    }
  }

  return {
    FALLBACK_PARTIAL,
    OFFLINE_HINT,
    esc,
    clip,
    renderStatusFeedback,
    renderOffline,
    init,
  };
})();

if (typeof window !== "undefined") {
  window.TalentForgeLlm = TalentForgeLlm;
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => TalentForgeLlm.init());
  } else {
    TalentForgeLlm.init();
  }
}
