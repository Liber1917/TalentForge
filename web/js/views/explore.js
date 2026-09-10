/* =========================================================
   TalentForge 方向探索视图（#/explore，M7 spec §5）
   - B→A 混合交互的 B 端（快照先行）：一键生成 3-5 张方向卡
     （一次 LLM 深推约 30-90 秒；POST /api/explore/snapshot 用
     AbortController 120s 超时——api.js 的 10s 不够长）
   - 资产盘点折叠区（details）：进入视图 GET /api/explore/asset-brief，
     渲染 技能簇/强信号/行为兴趣/硬边界 紧凑清单，先让用户纠错
     （D23 防线 c：用户校对兜底）再生成
   - 方向卡：scope 三口径徽章（track=terracotta 实底/lifestyle=
     琥珀描边/field=stone 描边，复用 verdict-badge 三态配色语义）
     + why_you 证据链折叠 + data_backed 双标记（数据✓/推理≈，
     D13 边界诚实：不可验证市场明确降级）+ 约束碰撞琥珀提示行
   - "深挖这个方向" → localStorage 写 tf_deep_dive_card（{title, scope}）
     → 跳 #/chat 由对话页接续深谈（A 端，chat.js 注入引导泡）
   - 进入视图时 GET /api/explore/directions 已有卡直接展示（不重生成）
   - fixtures 模式（USE_FIXTURES）：LOCAL_DIRECTION_FIXTURES 三口径
     各一张本地渲染；快照按钮 mock（禁用 1.2s 后刷新本地卡）
   渲染函数为纯字符串输出（文本一律 esc 转义），DOM 挂载分离，
   便于 node:test 直接断言。
   ========================================================= */

"use strict";

const TalentForgeExplore = (() => {
  /* ---------- 标签映射 ---------- */
  const SCOPE_LABEL = { track: "赛道", lifestyle: "活法", field: "行业" };
  /* why_you 证据种类（domain/direction.py EvidenceRef.kind） */
  const KIND_LABEL = { work: "作品", profile: "画像", behavior: "行为", dialogue: "对话" };

  const DIRECTIONS_EMPTY = "还没有方向卡——点「生成方向快照」，基于你已有的资产推一轮全景";
  const BRIEF_SUMMARY_TEXT = "资产盘点（先核对再生成——有误去画像页纠错）";
  const GENERATE_RESTING_TEXT = "生成方向快照";
  const GENERATE_RUNNING_TEXT = "探索中…（约1分钟）";
  /* 快照是一次 LLM 深推（约 30-90 秒），api.js 的 10s 超时不够 */
  const SNAPSHOT_TIMEOUT_MS = 120000;
  const DEEP_DIVE_KEY = "tf_deep_dive_card";

  /* ---------- 离线假数据（spec §5）：三口径各一张示例卡 ---------- */
  const LOCAL_DIRECTION_FIXTURES = [
    {
      card_id: "dir-demo-edge-ai",
      scope: "track",
      title: "边缘 AI 部署",
      why_you: [
        { kind: "work", ref: "github:demo/edge-infer", text: "MCU 推理引擎仓库，C++/Python 混合，142 commits 持续 14 个月" },
        { kind: "profile", ref: "claim-demo-sysdes-01", text: "分布式系统/系统设计深度积累，正在系统化准备面试" },
        { kind: "behavior", ref: "bilibili:edge-ai", text: "持续浏览端侧推理与模型量化内容" },
      ],
      market_evidence: "岗位库样本中「边缘 AI/端侧推理」相关岗约占 4%，薪资带 30-60K·15薪，嵌入式 × 架构实验的交叉组合溢价明显",
      data_backed: true,
      distance: "工程链路已通，缺 1-2 个可复现的部署案例与量化指标（延迟/功耗）背书",
      first_step: "两周内把 edge-infer 整理成带板卡、文档与指标的部署案例，挂到简历首位",
      constraint_check: ["端侧岗位多在硬件团队，面试偏底层——提前准备操作系统/体系结构问答"],
      confidence: 0.72,
      created_from: "",
    },
    {
      card_id: "dir-demo-startup-core",
      scope: "lifestyle",
      title: "初创核心工程师",
      why_you: [
        { kind: "profile", ref: "structural:cash_buffer", text: "现金缓冲约 6 个月，敢裸辞但更想骑驴找马" },
        { kind: "dialogue", ref: "turn-4", text: "996 可谈对价与弹性，竞业限制是硬边界" },
      ],
      market_evidence: "15-50 人初创核心岗薪资带 25-50K + 期权，对「既能铺基础设施又能碰业务」的工程师需求稳定",
      data_backed: true,
      distance: "技术面够，缺一封「早期员工」语境的推荐叙事与 founder 圈层的一段可见度",
      first_step: "列 10 家目标初创，找其中 3 家的前员工聊真实工时与期权行权史",
      constraint_check: [
        "期权流动性差，与「6 个月后见现金流」的缓冲规划存在张力",
        "部分初创合同含竞业条款——投前逐条核对",
      ],
      confidence: 0.64,
      created_from: "",
    },
    {
      card_id: "dir-demo-city-reprice",
      scope: "field",
      title: "上海 vs 新一线",
      why_you: [
        { kind: "profile", ref: "structural:city_constraints", text: "城市约束上海/长三角，支持网络集中在此" },
        { kind: "work", ref: "github:demo/raft-viewer", text: "开源作品 87 stars，跨城可见度已有基础" },
      ],
      market_evidence: "推理·置信中：同技能包在上海溢价约 20-30%、新一线生活成本低约 30%——跨城重定价基于行业常识推断，非岗位库实测",
      data_backed: false,
      distance: "若迁新一线：内推网络需重建（约 2-3 个月），生活成本同步下降",
      first_step: "各挑 5 个上海/新一线目标岗，用同一份画像分别生成报告，对比结论差异",
      constraint_check: ["海外远程岗的市场判断不可验证（Boss 数据只覆盖国内），决策需另找数据源"],
      confidence: 0.55,
      created_from: "",
    },
  ];

  /* 资产盘点本地示例：镜像 explore/engine.build_asset_brief 输出形状 */
  const LOCAL_ASSET_BRIEF = {
    basics: { years_experience: 3, skills: ["Python", "C++", "嵌入式"], desired_roles: ["边缘 AI 工程师"] },
    skill_clusters: [
      { language: "Python", repos: 6 },
      { language: "C", repos: 3 },
      { language: "C++", repos: 2 },
    ],
    strong_signals: [
      "[github] edge-infer（C++，142 commits）",
      "[github] raft-viewer（Python，142 commits）",
      "用户对分布式系统/系统设计有深度积累，正在系统化准备系统设计面试",
    ],
    behavior_interests: [
      "用户对后端开发中的异步编程技术有深入学习的兴趣",
      "用户正在准备系统设计面试，关注相关面试准备内容",
    ],
    structural_summary: {
      cash_buffer: "约6个月",
      stage: "3 年经验，中期跃迁阶段",
      city_constraints: ["上海", "长三角"],
      family_duty: "暂无重大家庭负担",
      support_network: ["前同事：2 名前同事在内推圈"],
      economic_independence: "经济独立，月度盈余约 4k",
      family_payback: "否",
      reservation_wage: "¥30–35万/年（CNY）",
      material_conditions: "",
      social_relations: "",
    },
    hard_boundaries: {
      deal_breakers: ["996", "竞业限制"],
      exploitation_redlines: ["996（硬边界）", "竞业限制（硬边界）"],
    },
  };

  /* 兜底骨架：与 web/partials/explore.html 保持一致（fetch 失败时注入） */
  const FALLBACK_PARTIAL = `
<div class="explore-layout">
  <header class="explore-head">
    <h2 class="explore-head__title">方向探索</h2>
    <p class="explore-head__hint">基于已有画像、作品与决策历史，向可能性空间搜索——先快照看全景，再挑一张深谈（三口径：赛道/活法/行业）</p>
  </header>
  <details class="explore-brief" id="explore-brief">
    <summary class="explore-brief__summary">${BRIEF_SUMMARY_TEXT}</summary>
    <div class="explore-brief__body" id="explore-brief-body" data-role="explore-brief-body"></div>
  </details>
  <div class="explore-actions">
    <button class="btn btn--primary" id="explore-generate" type="button" data-action="generate-snapshot">${GENERATE_RESTING_TEXT}</button>
    <p class="explore-actions__hint">一次深度推理，约需 1 分钟</p>
  </div>
  <div class="explore-cards" id="explore-cards" role="list" aria-label="方向卡列表"></div>
</div>`;

  /* ---------- 视图状态 ---------- */
  const state = {
    loaded: false,
    directions: [],
    generating: false,
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

  function useFixtures() {
    return typeof TalentForgeApi === "undefined" || TalentForgeApi.USE_FIXTURES;
  }

  /* ---------- 纯渲染函数（测试可直接断言） ---------- */

  /** scope → 徽章类名：track=terracotta 实底 / lifestyle=琥珀描边 / field=stone 描边
      （未知口径回退 track，同 workGradePill 缺省语义）。 */
  function scopeBadgeClass(scope) {
    const key = SCOPE_LABEL[scope] ? scope : "track";
    return `scope-badge scope-badge--${key}`;
  }

  /** why_you 证据链（EvidenceChain 样式，details 折叠；无 at 字段也可渲染）。 */
  function renderEvidenceChain(items, { label } = {}) {
    const list = Array.isArray(items) ? items : [];
    const summary = label || `证据链 · ${list.length} 条`;
    const rows = list.map((item) => {
      const kind = KIND_LABEL[item.kind] || item.kind || "";
      const excerpt = item.text ? clip(item.text, 48) : "";
      const at = item.at ? item.at : "";
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

  /** 盘点单组：overline 标签 + 紧凑清单（空组给"暂无记录"占位）。 */
  function renderBriefGroup(label, lines) {
    const items = (Array.isArray(lines) ? lines : [])
      .map((x) => (x === null || x === undefined ? "" : String(x).trim()))
      .filter(Boolean);
    const inner = items.length
      ? `<ul class="explore-brief__list">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
      : `<p class="explore-brief__empty">暂无记录</p>`;
    return `
        <section class="explore-brief__group" aria-label="${esc(label)}">
          <span class="overline">${esc(label)}</span>
          ${inner}
        </section>`;
  }

  /** 资产盘点紧凑清单（D23 防线 c）：技能簇/强信号/行为兴趣/硬边界四组。 */
  function renderAssetBrief(brief, reason) {
    if (!brief || typeof brief !== "object") {
      const why = reason ? `（${esc(reason)}）` : "";
      return `<p class="explore-brief__empty" role="status">暂无可盘点的资产${why}——先去画像页补充基础信息，或直接生成快照</p>`;
    }
    const clusters = (Array.isArray(brief.skill_clusters) ? brief.skill_clusters : [])
      .filter((c) => c && typeof c === "object")
      .map((c) => `${c.language || "?"} × ${Number(c.repos) || 0} 仓库`);
    const hb = (brief.hard_boundaries && typeof brief.hard_boundaries === "object") ? brief.hard_boundaries : {};
    const hardLines = [
      ...(Array.isArray(hb.deal_breakers) ? hb.deal_breakers : []),
      ...(Array.isArray(hb.exploitation_redlines) ? hb.exploitation_redlines : []),
    ];
    return `
        <div class="explore-brief__grid">
          ${renderBriefGroup("技能簇（作品语言分布）", clusters)}
          ${renderBriefGroup("强信号（强作品 + 已确认主张）", brief.strong_signals)}
          ${renderBriefGroup("行为兴趣（待验证主张）", brief.behavior_interests)}
          ${renderBriefGroup("硬边界与工作底线", hardLines)}
        </div>
        <p class="explore-brief__note">盘点有误？去 <a href="#/profile">画像页</a> 纠错后再生成，快照质量取决于这份底账。</p>`;
  }

  /** 单张方向卡：scope 徽章 + 置信/data_backed 标记 + 证据链折叠 +
      市场验证/差多远/第一步高亮卡/约束碰撞琥珀行 + 深挖按钮。 */
  function renderDirectionCard(card) {
    if (!card || typeof card !== "object") return "";
    const rawScope = String(card.scope || "");
    const scopeKey = SCOPE_LABEL[rawScope] ? rawScope : "track";
    const title = esc(card.title || "");
    const confidence = Math.round((Number(card.confidence) || 0) * 100);
    const databack = card.data_backed
      ? `<span class="direction-card__databack direction-card__databack--data">数据✓</span>`
      : `<span class="direction-card__databack direction-card__databack--inferred">推理≈</span>`;
    const whyYou = Array.isArray(card.why_you) ? card.why_you : [];
    const constraints = (Array.isArray(card.constraint_check) ? card.constraint_check : [])
      .map((c) => String(c ?? "").trim())
      .filter(Boolean);
    const constraintsHtml = constraints.length
      ? `<div class="direction-card__constraints" role="note">
          ${constraints.map((c) => `<p class="direction-card__constraint">⚠ ${esc(c)}</p>`).join("")}
        </div>`
      : "";
    return `
        <article class="card direction-card" data-card-id="${esc(card.card_id)}" data-scope="${esc(scopeKey)}" role="listitem">
          <header class="direction-card__head">
            <span class="${scopeBadgeClass(scopeKey)}">${esc(SCOPE_LABEL[scopeKey])}</span>
            <span class="direction-card__meta"><span>置信 ${confidence}%</span>${databack}</span>
          </header>
          <h3 class="direction-card__title">${title}</h3>
          ${renderEvidenceChain(whyYou, { label: `为什么是你 · ${whyYou.length} 条` })}
          ${card.market_evidence ? `<p class="direction-card__row"><span class="overline">市场验证</span>${esc(card.market_evidence)}</p>` : ""}
          ${card.distance ? `<p class="direction-card__row"><span class="overline">差多远</span>${esc(card.distance)}</p>` : ""}
          ${card.first_step ? `<p class="direction-card__step"><span class="overline">第一步</span>${esc(card.first_step)}</p>` : ""}
          ${constraintsHtml}
          <footer class="direction-card__actions">
            <button class="btn btn--primary btn--sm" type="button" data-action="deep-dive" data-card-title="${title}"
                    aria-label="深挖方向：${esc(clip(card.title, 20))}">深挖这个方向</button>
          </footer>
        </article>`;
  }

  /** 方向卡展区（空数据给引导文案）。 */
  function renderDirectionsList(directions) {
    const list = Array.isArray(directions) ? directions : [];
    if (!list.length) {
      return `<div class="explore-empty" role="status"><p>${esc(DIRECTIONS_EMPTY)}</p></div>`;
    }
    return list.map(renderDirectionCard).join("");
  }

  /** 快照生成态：加载（衬线斜体书房语气）/ 失败（risk 色）。 */
  function renderSnapshotStatus(kind, detail) {
    if (kind === "loading") {
      return `<div class="explore-status explore-status--loading" role="status" aria-live="polite">探索中…一次深度推理约 1 分钟，请稍候</div>`;
    }
    if (kind === "error") {
      return `<div class="explore-status explore-status--error" role="alert">生成失败：${esc(clip(detail || "请稍后重试", 60))}</div>`;
    }
    return "";
  }

  /* ---------- DOM 挂载与交互 ---------- */
  function getHost() {
    return document.getElementById("explore");
  }

  function getCardsEl() {
    return document.getElementById("explore-cards");
  }

  let partialPromise = null;
  function mountPartial() {
    if (partialPromise) return partialPromise;
    partialPromise = (async () => {
      const host = getHost();
      if (!host || host.querySelector(".explore-layout")) return;
      try {
        const res = await fetch("partials/explore.html");
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

  async function fetchJson(url, options) {
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      ...options,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /* 资产盘点：每次进入视图刷新（便宜、no-store，画像页可能刚纠错过）。 */
  async function loadBrief() {
    const body = document.getElementById("explore-brief-body");
    if (!body) return;
    if (useFixtures()) {
      body.innerHTML = renderAssetBrief(LOCAL_ASSET_BRIEF);
      return;
    }
    try {
      const data = await fetchJson("/api/explore/asset-brief");
      body.innerHTML = data && data.brief
        ? renderAssetBrief(data.brief)
        : renderAssetBrief(null, data && data.reason);
    } catch (err) {
      body.innerHTML = renderAssetBrief(null, "后端未启动");
    }
  }

  /* 已有方向卡直读展示（不重生成）：fixtures 用本地示例。 */
  async function loadDirections() {
    if (state.loaded) return;
    state.loaded = true;
    if (useFixtures()) {
      state.directions = LOCAL_DIRECTION_FIXTURES;
      renderCardsArea(renderDirectionsList(state.directions));
      return;
    }
    try {
      const data = await fetchJson("/api/explore/directions");
      state.directions = Array.isArray(data && data.directions) ? data.directions : [];
    } catch (err) {
      state.directions = [];
    }
    renderCardsArea(renderDirectionsList(state.directions));
  }

  function renderCardsArea(html) {
    const el = getCardsEl();
    if (el) el.innerHTML = html;
  }

  function setGenerating(running) {
    const btn = document.getElementById("explore-generate");
    if (!btn) return;
    btn.disabled = running;
    btn.textContent = running ? GENERATE_RUNNING_TEXT : GENERATE_RESTING_TEXT;
  }

  /* fixtures 模式 mock：禁用 1.2s 后刷新本地卡。 */
  async function mockSnapshot() {
    state.generating = true;
    setGenerating(true);
    renderCardsArea(renderSnapshotStatus("loading"));
    await new Promise((resolve) => setTimeout(resolve, 1200));
    state.directions = LOCAL_DIRECTION_FIXTURES;
    renderCardsArea(renderDirectionsList(state.directions));
    state.generating = false;
    setGenerating(false);
  }

  /* 快照生成：POST /api/explore/snapshot（AbortController 120s——
     一次 LLM 深推 30-90 秒，api.js 的 10s 超时不够）。 */
  async function generateSnapshot() {
    if (state.generating) return;
    if (useFixtures()) {
      await mockSnapshot();
      return;
    }
    state.generating = true;
    setGenerating(true);
    renderCardsArea(renderSnapshotStatus("loading"));
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SNAPSHOT_TIMEOUT_MS);
    try {
      const res = await fetch("/api/explore/snapshot", {
        method: "POST",
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data && data.ok === false) throw new Error(data.error || "生成失败");
      state.directions = Array.isArray(data && data.directions) ? data.directions : [];
      renderCardsArea(renderDirectionsList(state.directions));
    } catch (err) {
      const msg = err && err.name === "AbortError"
        ? "探索超时（超过 120 秒）——请稍后重试"
        : (err && err.message) || "未知错误";
      renderCardsArea(renderSnapshotStatus("error", msg) + renderDirectionsList(state.directions));
    } finally {
      clearTimeout(timer);
      state.generating = false;
      setGenerating(false);
    }
  }

  /** 深谈接续：写 localStorage tf_deep_dive_card → 跳对话页（A 端深谈）。 */
  function startDeepDive(btn) {
    const cardEl = btn.closest("[data-scope]");
    const payload = {
      title: btn.dataset.cardTitle || "",
      scope: cardEl ? cardEl.dataset.scope : "",
    };
    try {
      window.localStorage.setItem(DEEP_DIVE_KEY, JSON.stringify(payload));
    } catch (err) {
      /* localStorage 不可用（隐私模式等）：仍跳转，深谈引导退化为普通进入 */
    }
    if (window.TalentForgeRouter && typeof window.TalentForgeRouter.navigate === "function") {
      window.TalentForgeRouter.navigate("/chat");
    } else {
      window.location.hash = "#/chat";
    }
  }

  function onHostClick(evt) {
    const deepBtn = evt.target.closest("[data-action='deep-dive']");
    if (deepBtn) {
      evt.preventDefault();
      startDeepDive(deepBtn);
      return;
    }
    const genBtn = evt.target.closest("[data-action='generate-snapshot']");
    if (genBtn) {
      evt.preventDefault();
      generateSnapshot();
    }
  }

  function wireEvents() {
    const host = getHost();
    if (host) {
      host.addEventListener("click", onHostClick);
    }
  }

  function onEnterExplore() {
    mountPartial().then(() => {
      loadBrief();
      loadDirections();
    });
  }

  function init() {
    if (window.TalentForgeRouter && typeof window.TalentForgeRouter.onView === "function") {
      window.TalentForgeRouter.onView("explore", onEnterExplore);
    } else {
      window.addEventListener("route:change", (evt) => {
        if (evt.detail && evt.detail.view === "explore") onEnterExplore();
      });
    }
    if (window.TalentForgeRouter && window.TalentForgeRouter.currentPath() === "/explore") {
      onEnterExplore();
    }
  }

  return {
    SCOPE_LABEL,
    KIND_LABEL,
    LOCAL_DIRECTION_FIXTURES,
    LOCAL_ASSET_BRIEF,
    DIRECTIONS_EMPTY,
    BRIEF_SUMMARY_TEXT,
    GENERATE_RESTING_TEXT,
    GENERATE_RUNNING_TEXT,
    DEEP_DIVE_KEY,
    FALLBACK_PARTIAL,
    esc,
    clip,
    scopeBadgeClass,
    renderAssetBrief,
    renderBriefGroup,
    renderEvidenceChain,
    renderDirectionCard,
    renderDirectionsList,
    renderSnapshotStatus,
    init,
  };
})();

if (typeof window !== "undefined") {
  window.TalentForgeExplore = TalentForgeExplore;
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => TalentForgeExplore.init());
  } else {
    TalentForgeExplore.init();
  }
}
