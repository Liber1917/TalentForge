/* =========================================================
   TalentForge 平台源设置视图（#sources），参考 OpenBiliClaw 平台源页设计
   - 每个来源一张卡：卡面 = 名称 + 接入方式标签 + 接入状态徽章 +
     脱敏摘要；展开 = 接入方式说明 + 凭据粘贴框 + 保存 + 测试连接 + 状态行
    - Boss 直聘（kind=cookie）：粘贴浏览器复制的 cookie 串；留空保存
      不覆盖现有值（后端语义）；测试连接做轻量验证（真实外呼）
    - B站/知乎（kind=extension）：插件登录态采集，无需配置 cookie
    - GitHub/Gitee/arXiv（kind=public，M5 作品源）：展开输入
      用户名/作者名 → "拉取作品"按钮真调 POST /api/work/fetch
      （作品拉取无 fixtures 假数据，后端必须跑着；失败显示
      "后端未启动"），状态行显示 total/added/warnings
   - 凭据脱敏：后端只回传前4后4掩码（如 abcd****wxyz），
     页面无"复制原值"入口；状态徽章 none=琥珀 hold 语义、
     已配置=ok 绿、插件/公开=中性
   - 数据加载为真功能：直接 fetch("/api/sources")（不走 USE_FIXTURES
     base，无假数据模式）；失败时显示"后端未启动"占位
   渲染函数为纯字符串输出（文本一律 esc 转义），DOM 挂载分离，
   便于 node:test 直接断言。
   ========================================================= */

"use strict";

const TalentForgeSources = (() => {
  /* ---------- 标签映射（接入状态 → 中文 + 徽章语义色） ---------- */
  const SOURCE_LABEL = {
    env: "环境变量",
    saved: "已保存",
    jobclaw: "jobclaw 文件",
    none: "未配置",
    extension: "插件采集",
    public: "公开接口",
    config: "Web 配置",
  };
  const KIND_LABEL = {
    cookie: "需 cookie",
    extension: "插件取数",
    public: "公开接口",
    llm: "模型服务",
  };

  /* ---------- 作品源（M5 spec §5）：可配置拉取的公开源卡 ---------- */
  const WORK_KEYS = ["github", "gitee", "arxiv"];
  const WORK_INPUT_LABEL = { github: "用户名", gitee: "用户名", arxiv: "作者名" };
  const WORK_INPUT_PLACEHOLDER = {
    github: "如 octocat（GitHub 用户名）",
    gitee: "如 mindspore（Gitee 用户名）",
    arxiv: "如 Zhang San（作者名，姓在前）",
  };
  /* fetch body 字段名（routes_work.WorkFetchRequest 契约） */
  const WORK_FETCH_FIELD = { github: "github_user", gitee: "gitee_user", arxiv: "arxiv_author" };
  /* grade 中文映射（与后端 routes_work._GRADE_ZH 一致） */
  const GRADE_LABEL = { strong: "强", normal: "普通", weak: "弱" };

  /* 兜底骨架：与 web/partials/sources.html 保持一致（fetch 失败时注入） */
  const FALLBACK_PARTIAL = `
<div class="sources-layout">
  <header class="sources-head">
    <h2 class="sources-head__title">平台源</h2>
    <p class="sources-head__hint">管理各数据平台的接入方式与凭据</p>
    <p class="sources-head__hint sources-head__hint--warn">国内站（Boss/B站/知乎）请直连访问：开 VPN/代理可能被风控拦截——官网打不开或被弹回时，先关代理再试</p>
  </header>
  <div class="sources-list" id="sources-list" role="list" aria-label="平台源列表"></div>
</div>`;

  const OFFLINE_HINT = "后端未启动：请先运行 TalentForge 服务（127.0.0.1:8420），再回到此页查看平台源状态";
  const VERIFY_RUNNING_TEXT = "测试中…";

  /* ---------- 视图状态 ---------- */
  const state = {
    loaded: false,
    sources: [],
    offline: false,
  };

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

  /* ---------- 纯计算/渲染函数（测试可直接断言） ---------- */

  /** 接入状态 → 状态徽章语义类：none=琥珀 hold、已配置=ok 绿、插件/公开=中性灰。 */
  function pillClassForSource(source) {
    if (source === "none") return "status-pill status-pill--trial";
    if (source === "env" || source === "saved" || source === "jobclaw") {
      return "status-pill status-pill--active";
    }
    return "status-pill status-pill--archived";
  }

  /** 卡面脱敏摘要行：已配置显示掩码串，未配置显示提示。 */
  function renderMaskedLine(source) {
    const masked = String((source && source.status && source.status.masked) || "");
    const key = String((source && source.key) || "");
    if (key !== "boss") return "";
    if (!masked) {
      return `<p class="source-card__masked"><span class="source-card__masked-empty">尚未配置凭据——展开粘贴 cookie 后保存</span></p>`;
    }
    return `<p class="source-card__masked">当前凭据（脱敏）：<code>${esc(masked)}</code></p>`;
  }

  /** cookie 源展开区：说明 + 粘贴框（留空保存不覆盖）+ 保存/测试连接 + 状态行。 */
  function renderCookieExpand(source) {
    const key = esc(source.key);
    const qrEntry = key === "boss"
      ? `
          <div class="source-card__actions">
            <button class="btn btn--primary btn--sm" type="button" data-action="qr-start">扫码登录（推荐）</button>
          </div>
          <div class="qr-login" data-role="qr-login" hidden>
            <img class="qr-login__img" alt="Boss 直聘登录二维码" data-role="qr-img" />
            <p class="qr-login__hint">手机 Boss App 扫码 → 登录后自动保存 cookie（页面别关）</p>
          </div>`
      : "";
    return `
      <details class="source-card__expand">
        <summary class="source-card__summary">接入方式与设置</summary>
        <div class="source-card__body">
          <p class="source-card__note">${esc(source.note || "")}</p>
          <div class="overline">方式一：扫码登录</div>
          ${qrEntry}
          <div class="overline">方式二：粘贴 cookie</div>
          <textarea class="input source-card__textarea" id="source-input-${key}" rows="3"
                    placeholder="wt2=…; wbg=…（留空保存不覆盖现有值）"
                    autocomplete="off" spellcheck="false" data-role="source-input"></textarea>
          <div class="source-card__actions">
            <button class="btn btn--ghost btn--sm" type="button"
                    data-action="source-save" data-key="${key}">保存</button>
            <button class="btn btn--ghost btn--sm" type="button"
                    data-action="source-verify" data-key="${key}">测试连接</button>
          </div>
          <p class="source-card__status" role="status" aria-live="polite" data-role="source-status"></p>
        </div>
      </details>`;
  }

  /** 作品源展开区（M5 §5）：用户名/作者名输入 + "拉取作品"按钮 + 状态行（纯渲染）。 */
  function renderWorkExpand(source) {
    const key = esc(source.key);
    const label = WORK_INPUT_LABEL[source.key] || "用户名";
    const placeholder = esc(WORK_INPUT_PLACEHOLDER[source.key] || "如 用户名");
    return `
      <details class="source-card__expand">
        <summary class="source-card__summary">拉取作品</summary>
        <div class="source-card__body">
          <label class="overline" for="work-input-${key}">${esc(label)}</label>
          <input class="input source-card__work-input" id="work-input-${key}" type="text"
                 placeholder="${placeholder}"
                 autocomplete="off" spellcheck="false" data-role="work-user-input">
          <div class="source-card__actions">
            <button class="btn btn--primary btn--sm" type="button"
                    data-action="work-fetch" data-key="${key}">拉取作品</button>
          </div>
          <p class="source-card__status" role="status" aria-live="polite" data-role="source-status"></p>
        </div>
      </details>`;
  }

  /** LLM 模型服务展开区（M8）：base_url/model/api_key/并发 + 保存/测试连接 + 状态行（纯渲染）。 */
  function renderLlmExpand(source) {
    const key = esc(source.key);
    return `
      <details class="source-card__expand">
        <summary class="source-card__summary">模型服务设置</summary>
        <div class="source-card__body">
          <label class="overline" for="llm-base-url-${key}">Base URL</label>
          <input class="input source-card__llm-input" id="llm-base-url-${key}" type="text"
                 placeholder="https://api.openai.com/v1"
                 autocomplete="off" spellcheck="false" data-role="llm-base-url">
          <label class="overline" for="llm-model-${key}">模型</label>
          <input class="input source-card__llm-input" id="llm-model-${key}" type="text"
                 placeholder="gpt-4o-mini"
                 autocomplete="off" spellcheck="false" data-role="llm-model">
          <label class="overline" for="llm-key-${key}">API Key</label>
          <input class="input source-card__llm-input" id="llm-key-${key}" type="password"
                 placeholder="sk-…（留空保存不覆盖现有值）"
                 autocomplete="off" spellcheck="false" data-role="llm-api-key">
          <label class="overline" for="llm-conc-${key}">决策匹配并发度</label>
          <input class="input source-card__llm-input" id="llm-conc-${key}" type="number" min="1" max="16"
                 placeholder="5" data-role="llm-concurrency">
          <div class="source-card__actions">
            <button class="btn btn--primary btn--sm" type="button"
                    data-action="llm-save" data-key="${key}">保存</button>
            <button class="btn btn--ghost btn--sm" type="button"
                    data-action="llm-verify" data-key="${key}">测试连接</button>
          </div>
          <p class="source-card__status" role="status" aria-live="polite" data-role="source-status"></p>
        </div>
      </details>`;
  }

  /** 单张源卡：卡面（名称/方式标签/状态徽章/脱敏摘要）+（cookie 源）展开区。 */
  function renderSourceCard(source) {
    if (!source || typeof source !== "object") return "";
    const key = esc(source.key || "");
    const name = esc(source.name || source.key || "");
    const kindKey = String(source.kind || "");
    const kindLabel = KIND_LABEL[kindKey] || kindKey;
    const status = (source.status && source.status.source) || "none";
    const stateLabel = SOURCE_LABEL[status] || status;
    const kindTag = kindLabel ? `<span class="source-card__kind">${esc(kindLabel)}</span>` : "";
    /* 风控强的站（nav=self，如 Boss）在当前 tab 内经 goto.html 跳转：本 tab 有浏览历史，
       站点反爬的 window.close() 会被浏览器拒绝；target=_blank 弹出的 tab 永远可被关（实测）。 */
    const sameTab = String(source.nav || "blank") === "self";
    const attrs = sameTab
      ? `aria-label="在当前页打开 ${name} 官网（按浏览器返回键回来）"`
      : `target="_blank" rel="noopener noreferrer" aria-label="打开 ${name} 官网"`;
    const homeLink = key
      ? `<a class="source-card__site" href="goto.html?key=${key}" ${attrs}>官网 ↗</a>`
      : "";
    const expand = kindKey === "cookie"
      ? renderCookieExpand(source)
      : (WORK_KEYS.includes(String(source.key)) ? renderWorkExpand(source)
        : (kindKey === "llm" ? renderLlmExpand(source) : ""));
    return `
        <article class="card source-card" data-source-key="${key}" role="listitem">
          <header class="source-card__head">
            <h3 class="source-card__name">${name}</h3>
            ${kindTag}
            <span class="${pillClassForSource(status)}">${esc(stateLabel)}</span>
            ${homeLink}
          </header>
          ${renderMaskedLine(source)}
          ${source.note && kindKey !== "cookie" ? `<p class="source-card__note source-card__note--plain">${esc(source.note)}</p>` : ""}
          ${expand}
        </article>`;
  }

  /** 操作后的状态行反馈：已保存 / 连接正常（ok）/ 已失效（risk）/ 网络错误（risk）/ 作品拉取结果。 */
  function renderStatusFeedback(kind, detail) {
    if (kind === "saved") {
      return `<span class="status-pill status-pill--active">已保存</span> <a class="source-next-link" href="#/jobs">去工作台生成报告 →</a>`;
    }
    if (kind === "verify-ok") {
      return `<span class="status-pill status-pill--active">连接正常</span>`;
    }
    if (kind === "verify-invalid") {
      return `<span class="status-pill status-pill--risk">cookie 已失效，请重新粘贴</span>`;
    }
    if (kind === "work-fetch-ok") {
      const d = detail || {};
      const warnings = Array.isArray(d.warnings) ? d.warnings : [];
      const firstWarn = warnings.length ? `（${esc(clip(String(warnings[0]), 24))}）` : "";
      const warnText = warnings.length ? `，警告 ${warnings.length} 项${firstWarn}` : "";
      return `<span class="status-pill status-pill--active">拉取 ${Number(d.total_fetched) || 0} 条 · 新增 ${Number(d.added) || 0}${warnText}</span> <a class="source-next-link" href="#/profile">去画像页校对 →</a>`;
    }
    if (kind === "work-fetch-empty") {
      return `<span class="status-pill status-pill--trial">请先输入${esc(detail || "用户名")}</span>`;
    }
    if (kind === "error") {
      return `<span class="status-pill status-pill--risk">${esc(clip(detail || "操作失败，请稍后重试", 40))}</span>`;
    }
    return "";
  }

  /** 后端未启动占位卡。 */
  function renderOffline() {
    return `
        <div class="source-offline" role="status">
          <p>${esc(OFFLINE_HINT)}</p>
        </div>`;
  }

  /** 源卡列表（空数据时也给出占位，与离线区分）。 */
  function renderSourcesList(sources, offline) {
    if (offline) return renderOffline();
    const list = Array.isArray(sources) ? sources : [];
    return list.map(renderSourceCard).join("");
  }

  /* ---------- DOM 挂载与交互 ---------- */
  function getHost() {
    return document.getElementById("sources");
  }

  function getListEl() {
    return document.getElementById("sources-list");
  }

  let partialPromise = null;
  function mountPartial() {
    if (partialPromise) return partialPromise;
    partialPromise = (async () => {
      const host = getHost();
      if (!host || host.querySelector(".sources-layout")) return;
      try {
        const res = await fetch("partials/sources.html");
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

  /* 真功能数据加载：直接 fetch("/api/sources")，绕过 USE_FIXTURES base（无假数据模式）。 */
  async function loadSources() {
    state.loaded = true;
    try {
      const res = await fetch("/api/sources", {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.sources = Array.isArray(data && data.sources) ? data.sources : [];
      state.offline = false;
    } catch (err) {
      state.offline = true;
      state.sources = [];
    }
    renderAll();
  }

  function renderAll() {
    const listEl = getListEl();
    if (!listEl) return;
    const openStates = {};
    listEl.querySelectorAll(".source-card__expand").forEach((el) => {
      const card = el.closest("[data-source-key]");
      if (card) openStates[card.dataset.sourceKey] = el.open;
    });
    listEl.innerHTML = renderSourcesList(state.sources, state.offline);
    Object.entries(openStates).forEach(([key, open]) => {
      if (!open) return;
      const card = listEl.querySelector(`[data-source-key="${key}"] .source-card__expand`);
      if (card) card.open = true;
    });
    if (typeof document !== "undefined") {
      listEl.querySelectorAll("[data-source-key='llm'] .source-card__expand").forEach((el) => {
        if (el.open && !el.dataset.loaded) {
          el.dataset.loaded = "1";
          loadLlmFormInto(el.closest("[data-source-key='llm']"));
        }
      });
    }
  }

  function setStatusLine(key, html) {
    const listEl = getListEl();
    if (!listEl) return;
    const card = listEl.querySelector(`[data-source-key="${key}"]`);
    const line = card && card.querySelector("[data-role='source-status']");
    if (line) line.innerHTML = html;
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

  async function saveCredential(key, input) {
    const value = input ? input.value : "";
    setStatusLine(key, "");
    try {
      const data = await requestJson(`/api/sources/${encodeURIComponent(key)}/credential`, {
        method: "POST",
        body: JSON.stringify({ cookie: value }),
      });
      state.sources = state.sources.map((s) => (
        s && s.key === key ? { ...s, status: data.status } : s
      ));
      renderAll();
      setStatusLine(key, renderStatusFeedback("saved"));
      if (input) input.value = "";
    } catch (err) {
      setStatusLine(key, renderStatusFeedback("error", "保存失败：后端未启动或不可写"));
    }
  }

  async function verifyConnection(key, btn) {
    const original = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = VERIFY_RUNNING_TEXT;
    }
    try {
      const data = await requestJson(`/api/sources/${encodeURIComponent(key)}/verify`, {
        method: "POST",
      });
      setStatusLine(key, renderStatusFeedback(data && data.ok ? "verify-ok" : "verify-invalid"));
    } catch (err) {
      setStatusLine(key, renderStatusFeedback("error", "测试失败：后端未启动"));
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = original || "测试连接";
      }
    }
  }

  let qrPollTimer = null;

  /* 作品拉取（M5）：真功能直连后端 POST /api/work/fetch（不走 USE_FIXTURES base，
     无假数据模式）；失败提示后端未启动。 */
  async function fetchWorks(key, btn) {
    const card = btn ? btn.closest("[data-source-key]") : null;
    const input = card ? card.querySelector("[data-role='work-user-input']") : null;
    const value = input ? input.value.trim() : "";
    if (!value) {
      setStatusLine(key, renderStatusFeedback("work-fetch-empty", WORK_INPUT_LABEL[key] || "用户名"));
      if (input) input.focus();
      return;
    }
    const original = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "拉取中…";
    }
    setStatusLine(key, "");
    const body = { github_user: "", gitee_user: "", arxiv_author: "" };
    body[WORK_FETCH_FIELD[key] || "github_user"] = value;
    try {
      const data = await requestJson("/api/work/fetch", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setStatusLine(key, renderStatusFeedback("work-fetch-ok", data));
    } catch (err) {
      setStatusLine(key, renderStatusFeedback("error", "拉取失败：后端未启动"));
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = original || "拉取作品";
      }
    }
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store", ...options });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function startQrLogin(host) {
    const box = host.querySelector("[data-role='qr-login']");
    const img = host.querySelector("[data-role='qr-img']");
    if (!box || !img) return;
    box.hidden = false;
    img.alt = "正在生成二维码…";
    try {
      await fetchJson("/api/sources/boss/qr-login/start", { method: "POST" });
    } catch (err) {
      img.alt = "启动失败：后端未启动";
      return;
    }
    clearInterval(qrPollTimer);
    qrPollTimer = setInterval(async () => {
      try {
        const status = await fetchJson("/api/sources/boss/qr-login/status");
        if (status.state === "success") {
          clearInterval(qrPollTimer);
          img.alt = "登录成功，cookie 已保存";
          loadSources();
          return;
        }
        if (status.state === "failed") {
          clearInterval(qrPollTimer);
          img.alt = `登录失败：${status.error || "未知错误"}`;
          return;
        }
        const qr = await fetchJson("/api/sources/boss/qr-login/qr-image");
        if (qr.png_base64) img.src = `data:image/png;base64,${qr.png_base64}`;
      } catch (err) {
        /* 单次轮询失败静默，下一轮重试 */
      }
    }, 2500);
  }

  /** 保存 LLM 设置：POST /api/llm/settings（merge，key 留空不覆盖）；成功后刷新卡面状态。 */
  async function saveLlmSettings(key, card) {
    const get = (role) => {
      const el = card && card.querySelector(`[data-role='${role}']`);
      return el ? el.value : "";
    };
    const body = {
      base_url: get("llm-base-url"),
      model: get("llm-model"),
      match_concurrency: Number(get("llm-concurrency")) || undefined,
    };
    const apiKey = get("llm-api-key");
    if (apiKey.trim()) body.api_key = apiKey.trim();
    setStatusLine(key, "");
    try {
      const data = await requestJson("/api/llm/settings", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (data && data.settings) {
        state.sources = state.sources.map((s) => (
          s && s.key === key ? { ...s, status: { source: "config", masked: "" } } : s
        ));
        fillLlmForm(card, data.settings);
      }
      setStatusLine(key, renderStatusFeedback("saved"));
    } catch (err) {
      setStatusLine(key, renderStatusFeedback("error", "保存失败：后端未启动或不可写"));
    }
  }

  /** 测试 LLM 连接：POST /api/llm/settings/verify（提交配置临时外呼，不落盘）。 */
  async function verifyLlmSettings(key, btn) {
    const card = btn ? btn.closest("[data-source-key]") : null;
    const get = (role) => {
      const el = card && card.querySelector(`[data-role='${role}']`);
      return el ? el.value : "";
    };
    const body = {
      base_url: get("llm-base-url"),
      model: get("llm-model"),
    };
    const apiKey = get("llm-api-key");
    if (apiKey.trim()) body.api_key = apiKey.trim();
    const original = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "测试中…";
    }
    setStatusLine(key, "");
    try {
      const data = await requestJson("/api/llm/settings/verify", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (data && data.ok) {
        setStatusLine(key, renderStatusFeedback("verify-ok", data));
      } else {
        setStatusLine(key, renderStatusFeedback("error", (data && data.detail) || "连接失败"));
      }
    } catch (err) {
      setStatusLine(key, renderStatusFeedback("error", "测试失败：后端未启动"));
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = original || "测试连接";
      }
    }
  }

  /** 展开 LLM 卡时懒加载当前设置回填表单（GET /api/llm/settings，含生效来源）。 */
  async function loadLlmFormInto(card) {
    if (!card) return;
    try {
      const data = await requestJson("/api/llm/settings", { method: "GET" });
      if (data && data.settings) fillLlmForm(card, data.settings);
      if (data && data.source) {
        const status = card.querySelector("[data-role='source-status']");
        if (status) status.textContent = `当前生效来源：${data.source}`;
      }
    } catch (err) {
      /* 后端未启动：留空表单，用户仍可填后点保存 */
    }
  }

  /** 回填 LLM 表单：GET /api/llm/settings 的掩码视图填入输入框（key 显示掩码占位，不填值）。 */
  function fillLlmForm(card, settings) {
    if (!card || !settings) return;
    const base = card.querySelector("[data-role='llm-base-url']");
    const model = card.querySelector("[data-role='llm-model']");
    const key = card.querySelector("[data-role='llm-api-key']");
    const conc = card.querySelector("[data-role='llm-concurrency']");
    if (base && settings.base_url) base.value = settings.base_url;
    if (model && settings.model) model.value = settings.model;
    if (key && settings.api_key) key.placeholder = `已配置 ${settings.api_key}（留空不覆盖）`;
    if (conc && settings.match_concurrency) conc.value = settings.match_concurrency;
  }

  function onHostClick(evt) {
    const workBtn = evt.target.closest("[data-action='work-fetch']");
    if (workBtn) {
      evt.preventDefault();
      fetchWorks(workBtn.dataset.key || "", workBtn);
      return;
    }
    const llmSaveBtn = evt.target.closest("[data-action='llm-save']");
    if (llmSaveBtn) {
      evt.preventDefault();
      const card = llmSaveBtn.closest("[data-source-key]");
      saveLlmSettings(card ? card.dataset.sourceKey : "", card);
      return;
    }
    const llmVerifyBtn = evt.target.closest("[data-action='llm-verify']");
    if (llmVerifyBtn) {
      evt.preventDefault();
      const card = llmVerifyBtn.closest("[data-source-key]");
      verifyLlmSettings(card ? card.dataset.sourceKey : "", llmVerifyBtn);
      return;
    }
    const qrBtn = evt.target.closest("[data-action='qr-start']");
    if (qrBtn) {
      evt.preventDefault();
      const host = qrBtn.closest("[data-source-key]");
      if (host) startQrLogin(host);
      return;
    }
    const saveBtn = evt.target.closest("[data-action='source-save']");
    if (saveBtn) {
      evt.preventDefault();
      const card = saveBtn.closest("[data-source-key]");
      const input = card && card.querySelector("[data-role='source-input']");
      saveCredential(card ? card.dataset.sourceKey : "", input);
      return;
    }
    const verifyBtn = evt.target.closest("[data-action='source-verify']");
    if (verifyBtn) {
      evt.preventDefault();
      const card = verifyBtn.closest("[data-source-key]");
      verifyConnection(card ? card.dataset.sourceKey : "", verifyBtn);
    }
  }

  function wireEvents() {
    const host = getHost();
    if (host) {
      host.addEventListener("click", onHostClick);
    }
  }

  function onEnterSources() {
    mountPartial().then(() => {
      if (!state.loaded) loadSources();
    });
  }

  function init() {
    if (window.TalentForgeRouter && typeof window.TalentForgeRouter.onView === "function") {
      window.TalentForgeRouter.onView("sources", onEnterSources);
    } else {
      window.addEventListener("route:change", (evt) => {
        if (evt.detail && evt.detail.view === "sources") onEnterSources();
      });
    }
    if (window.TalentForgeRouter && window.TalentForgeRouter.currentPath() === "/sources") {
      onEnterSources();
    }
  }

  return {
    SOURCE_LABEL,
    KIND_LABEL,
    GRADE_LABEL,
    WORK_KEYS,
    OFFLINE_HINT,
    FALLBACK_PARTIAL,
    esc,
    clip,
    pillClassForSource,
    renderMaskedLine,
    renderSourceCard,
    renderWorkExpand,
    renderLlmExpand,
    renderStatusFeedback,
    renderOffline,
    renderSourcesList,
    init,
  };
})();

if (typeof window !== "undefined") {
  window.TalentForgeSources = TalentForgeSources;
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => TalentForgeSources.init());
  } else {
    TalentForgeSources.init();
  }
}
