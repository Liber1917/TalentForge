/* =========================================================
   TalentForge 画像面板视图（#profile）
   - 四 tab（待定池/叙事/效用/结构位置）：tablist/tab/tabpanel
     ARIA 模式（DESIGN.md §7），纯前端切换，与路由无关
   - 待定池：narrative_claims 中 trial 态渲染 ClaimCard（结构
     同 chat.js：status-pill--trial + 置信 + 证据数 + EvidenceChain
     details + 确认/驳回按钮）；confirm→active（evidence_count+1）、
     reject→archived，fixtures 模式本地乐观更新 + 更新顶部待定池
     计数，真模式调端点；active/archived 进折叠区
   - 叙事轨：identity（衬线大字引言）+ values（标签 pill 组）
     + deep_drives（列表）
    - 效用轨：utility_preferences 逐条渲染（attribute + ordering
      排序，如 薪资：40万以上 > 30-40万 > 20-30万；evidence 非空时
      追加小字"（含 N 次决策回流）"，M4 反馈闭环）
   - 结构位置：D17 八格卡片网格（2 列，>1024px 3 列）+ 剥削敏感带
     /再生产账单/流动性区块；market_assessment 存在即标注"待数据积累"
     （D17 市场侧灰置，用户只填自己那半）
   - 简历校对：profile.resume_review 存在则渲染 抽取 vs 原文 diff
     视图（逐项确认）；fixtures 模式 mock 示例区块；否则"未上传简历"
   - 导出 JSON：fixtures 模式本地 Blob 下载；真模式 GET /profile/export
   - 顶部待定池计数：与 chat.js 同计算（profile.narrative_claims 中
     trial 态主张数），写入共享 #pending-count 徽章
   渲染函数为纯字符串输出（文本一律 esc 转义），DOM 层通过 <template>
   解析后挂载，便于 node:test 直接断言。
   ========================================================= */

"use strict";

const TalentForgeProfile = (() => {
  /* ---------- 标签映射（DESIGN.md §2/§5） ---------- */
  const STATE_LABEL = { trial: "待验证", active: "已确认", archived: "已归档" };
  const KIND_LABEL = {
    jd: "JD 原文",
    resume: "简历",
    dialogue: "对话",
    feedback: "反馈",
    behavior: "行为",
    system: "系统",
  };
  const ATTR_LABEL = {
    salary: "薪资",
    work_mode: "工作模式",
    location: "地点",
    company_type: "公司类型",
    tech_stack: "技术栈",
  };
  const POOL_EMPTY = "还没有待验证的主张——浏览 B站/知乎 或聊聊你自己，我会开始留意";

  /* ---------- 离线假数据：镜像 talentforge/api/fixtures.py get_fixture_profile ---------- */
  const LOCAL_FIXTURE_PROFILE = {
    name: "示例候选人（Demo）",
    years_experience: 3,
    skills: ["Python", "后端开发", "分布式系统"],
    desired_roles: ["后端工程师"],
    preferred_locations: ["深圳"],
    deal_breakers: ["996"],
    narrative: {
      identity: "深耕后端基础设施的工程师",
      values: ["技术深度", "工作生活平衡", "长期成长"],
      deep_drives: ["系统设计深度"],
    },
    utility_preferences: {
      salary: { attribute: "salary", ordering: ["40万以上", "30-40万", "20-30万"] },
      work_mode: { attribute: "work_mode", ordering: ["弹性工时", "标准双休", "大小周"] },
      location: { attribute: "location", ordering: ["深圳南山", "深圳福田", "深圳全城"] },
      company_type: { attribute: "company_type", ordering: ["中厂", "大厂", "创业公司"] },
      tech_stack: { attribute: "tech_stack", ordering: ["Python", "Go", "Java"] },
    },
    structural_position: {
      cash_buffer: "约6个月",
      stage: "3 年经验，处于中期跃迁阶段，计划 6-12 个月内完成一次关键跳槽",
      city_constraints: ["深圳", "珠三角"],
      family_duty: "暂无重大家庭负担，可接受跨城通勤",
      support_network: [
        { kind: "前同事", note: "2 名前同事在内推圈，可提供内推" },
        { kind: "导师", note: "前组长可作为背调联系人" },
      ],
      economic_independence: "经济独立，无重大负债，月度盈余约 4k",
      family_payback: false,
      reservation_wage: { min_annual: 300000, max_annual: 350000, currency: "CNY" },
      market_assessment: {},
      exploitation_redlines: [
        { kind: "996", stance: "never" },
        { kind: "竞业限制", stance: "never" },
        { kind: "无偿加班", stance: "never" },
      ],
      reproduction_costs: {
        housing: "月租 3500，约占收入 20%",
        commute: "单程 40 分钟",
        food: "公司周边餐饮日均约 60",
        skill_half_life_years: 2.0,
      },
      mobility: { dare_bare_quit: true, note: "6 个月现金缓冲，敢裸辞但更想骑驴找马" },
    },
    narrative_claims: [
      {
        claim_id: "claim-demo-01",
        text: "用户对后端开发中的异步编程技术有深入学习的兴趣",
        state: "trial",
        evidence_count: 0,
        confidence: 0.9,
        sources: [{ kind: "behavior", ref: "demo-5", at: "2026-08-21T09:04:00+00:00" }],
      },
      {
        claim_id: "claim-demo-02",
        text: "用户正在准备系统设计面试，关注相关面试准备内容",
        state: "trial",
        evidence_count: 0,
        confidence: 0.95,
        sources: [{ kind: "behavior", ref: "demo-5", at: "2026-08-21T09:04:00+00:00" }],
      },
      {
        claim_id: "claim-demo-03",
        text: "用户对分布式系统设计中的一致性协议（如Raft、Paxos）有研究需求",
        state: "trial",
        evidence_count: 0,
        confidence: 0.85,
        sources: [{ kind: "behavior", ref: "demo-5", at: "2026-08-21T09:04:00+00:00" }],
      },
      {
        claim_id: "claim-demo-active-01",
        text: "用户把 996 视为硬边界，除非给足对价与时间弹性否则不投",
        state: "active",
        evidence_count: 1,
        confidence: 0.9,
        sources: [
          { kind: "dialogue", ref: "demo-chat-confirm", at: "2026-08-21T09:04:00+00:00" },
        ],
      },
    ],
  };

  /* 简历校对 mock：演示 抽取文本 vs 原文 的 diff 视图（spec §3） */
  const LOCAL_FIXTURE_RESUME_REVIEW = {
    file: "resume_demo_2026.pdf",
    items: [
      {
        field: "identity",
        label: "一句话定位",
        original: "深耕后端基础设施的工程师",
        extracted: "深耕后端基础设施的工程师，三年分布式系统经验",
      },
      {
        field: "skills",
        label: "技能",
        original: "Python · 后端开发 · 分布式系统",
        extracted: "Python · Go · 分布式系统 · 消息队列",
      },
      {
        field: "years_experience",
        label: "工作年限",
        original: "3 年",
        extracted: "3 年 4 个月",
      },
    ],
  };

  /* 兜底骨架：与 web/partials/profile.html 保持一致（fetch 失败时注入） */
  const FALLBACK_PARTIAL = `
<div class="profile-layout">
  <header class="profile-head">
    <div class="profile-head__text">
      <h2 class="profile-head__name" id="profile-name"></h2>
      <p class="profile-head__identity" id="profile-identity"></p>
    </div>
    <button class="btn btn--secondary" id="profile-export" type="button">导出 JSON</button>
  </header>

  <div class="profile-tabs" id="profile-tabs" role="tablist" aria-label="画像区块">
    <button class="profile-tab is-active" type="button" role="tab" id="tab-pool" aria-selected="true" aria-controls="panel-pool" data-tab="pool">待定池</button>
    <button class="profile-tab" type="button" role="tab" id="tab-narrative" aria-selected="false" aria-controls="panel-narrative" data-tab="narrative">叙事</button>
    <button class="profile-tab" type="button" role="tab" id="tab-utility" aria-selected="false" aria-controls="panel-utility" data-tab="utility">效用</button>
    <button class="profile-tab" type="button" role="tab" id="tab-structural" aria-selected="false" aria-controls="panel-structural" data-tab="structural">结构位置</button>
  </div>

  <div class="profile-panel" id="panel-pool" role="tabpanel" aria-labelledby="tab-pool" tabindex="0"></div>
  <div class="profile-panel" id="panel-narrative" role="tabpanel" aria-labelledby="tab-narrative" tabindex="0" hidden></div>
  <div class="profile-panel" id="panel-utility" role="tabpanel" aria-labelledby="tab-utility" tabindex="0" hidden></div>
  <div class="profile-panel" id="panel-structural" role="tabpanel" aria-labelledby="tab-structural" tabindex="0" hidden></div>

  <section class="profile-resume" id="profile-resume" aria-label="简历校对"></section>
</div>`;

  /* ---------- 视图状态 ---------- */
  const state = {
    loaded: false,
    profile: null,
    activeTab: "pool",
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

  /* ---------- 纯计算/渲染函数（测试可直接断言） ---------- */

  /** 待定池计数：profile.narrative_claims 中 trial 态主张数（同 chat.js 语义）。 */
  function countTrialClaims(claims) {
    let n = 0;
    for (const c of claims || []) {
      if (c && c.state === "trial") n += 1;
    }
    return n;
  }

  /** 八格/区块单元格值格式化：字符串/数字/布尔/数组/对象（叶子一律 esc）。 */
  function fmtValue(v) {
    if (v === null || v === undefined || v === "") return "";
    if (typeof v === "boolean") return v ? "是" : "否";
    if (typeof v === "number") return String(v);
    if (Array.isArray(v)) {
      return v.map(fmtValue).filter(Boolean).join("、");
    }
    if (typeof v === "object") {
      if (typeof v.min_annual === "number" || typeof v.max_annual === "number") {
        const min = Math.round((Number(v.min_annual) || 0) / 10000);
        const max = Math.round((Number(v.max_annual) || 0) / 10000);
        return `¥${min}–${max}万/年${v.currency ? `（${esc(v.currency)}）` : ""}`;
      }
      if (typeof v.kind === "string") {
        return `${esc(v.kind)}：${fmtValue(v.note ?? "")}`;
      }
      return Object.entries(v)
        .map(([k, val]) => `${esc(k)}：${fmtValue(val)}`)
        .filter(Boolean)
        .join("；");
    }
    return esc(String(v));
  }

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

  /** 待定池 tab：trial 列表 + active/archived 折叠区。 */
  function renderPoolTab(claims) {
    const list = Array.isArray(claims) ? claims : [];
    const trial = list.filter((c) => c && c.state === "trial");
    const active = list.filter((c) => c && c.state === "active");
    const archived = list.filter((c) => c && c.state === "archived");

    const trialHtml = trial.length
      ? `<div class="pool-trial" role="list" aria-label="待验证主张">${trial.map(renderClaimCard).join("")}</div>`
      : `<p class="pool-empty" role="status">${esc(POOL_EMPTY)}</p>`;

    const activeHtml = active.length
      ? `<details class="pool-fold" open>
           <summary class="pool-fold__summary">已确认 ${active.length} 条</summary>
           <div class="pool-fold__list">${active.map(renderClaimCard).join("")}</div>
         </details>`
      : "";

    const archivedHtml = archived.length
      ? `<details class="pool-fold">
           <summary class="pool-fold__summary">已归档 ${archived.length} 条</summary>
           <div class="pool-fold__list">${archived.map(renderClaimCard).join("")}</div>
         </details>`
      : "";

    return `
        <div class="pool">
          ${trialHtml}
          ${activeHtml}
          ${archivedHtml}
        </div>`;
  }

  /** 叙事轨 tab：identity 引言 + values 标签组 + deep_drives 列表。 */
  function renderNarrativeTab(narrative) {
    const n = narrative || {};
    const identity = String(n.identity || "").trim();
    const values = Array.isArray(n.values) ? n.values : [];
    const drives = Array.isArray(n.deep_drives) ? n.deep_drives : [];
    const valuePills = values.length
      ? `<div class="tag-pills">${values.map((v) => `<span class="tag-pill">${esc(v)}</span>`).join("")}</div>`
      : "";
    const driveList = drives.length
      ? `<ul class="narrative__drives">${drives.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>`
      : "";
    return `
        <div class="narrative">
          ${identity ? `<blockquote class="narrative__identity">${esc(identity)}</blockquote>` : ""}
          ${valuePills ? `
          <section class="profile-section" aria-label="价值观">
            <span class="overline">价值观</span>
            ${valuePills}
          </section>` : ""}
          ${driveList ? `
          <section class="profile-section" aria-label="深层驱动">
            <span class="overline">深层驱动</span>
            ${driveList}
          </section>` : ""}
        </div>`;
  }

  /** 效用轨 tab：每条偏好 = 属性名 + ordering 排序展示；evidence 非空追加回流计数小字（M4）。 */
  function renderUtilityTab(prefs) {
    const entries = Object.entries(prefs || {});
    if (!entries.length) {
      return `<p class="pool-empty" role="status">还没有记录效用偏好。</p>`;
    }
    return `
        <ul class="pref-list">
          ${entries.map(([attr, pref]) => {
            const prefObj = (pref && typeof pref === "object") ? pref : {};
            const attrKey = prefObj.attribute || attr;
            const label = ATTR_LABEL[attrKey] || attrKey || attr;
            const ordering = Array.isArray(prefObj.ordering) ? prefObj.ordering : [];
            const evidence = Array.isArray(prefObj.evidence) ? prefObj.evidence : [];
            const orderHtml = ordering
              .map((o, i) => (i ? `<span class="pref-row__arrow">›</span>${esc(o)}` : esc(o)))
              .join("");
            const evidenceHtml = evidence.length
              ? `<span class="pref-row__evidence">（含 ${evidence.length} 次决策回流）</span>`
              : "";
            return `
          <li class="card pref-row">
            <span class="overline">${esc(label)}</span>
            <p class="pref-row__order">${orderHtml || `<span class="eight-cell__empty">未填写</span>`}${evidenceHtml}</p>
          </li>`;
          }).join("")}
        </ul>`;
  }

  /** 剥削敏感带：每条 stance 语义化（never → 硬边界不可妥协）。 */
  function renderRedlines(list) {
    return `<ul class="eight-block__list">${(Array.isArray(list) ? list : []).map((r) => {
      const stance = r.stance === "never" ? "硬边界 · 不可妥协" : esc(r.stance || "");
      return `<li>${esc(r.kind)}${stance ? `（${stance}）` : ""}</li>`;
    }).join("")}</ul>`;
  }

  function renderReproduction(costs) {
    const labels = {
      housing: "住房",
      commute: "通勤",
      food: "餐饮",
      skill_half_life_years: "技能半衰期",
    };
    return `<ul class="eight-block__list">${Object.entries(costs || {}).map(([k, v]) => {
      const label = labels[k] || k;
      const value = k === "skill_half_life_years" ? `${v} 年` : String(v);
      return `<li>${esc(label)}：${esc(value)}</li>`;
    }).join("")}</ul>`;
  }

  function renderMobility(mob) {
    const quit = mob.dare_bare_quit ? "敢裸辞" : "不敢裸辞";
    const note = String(mob.note || "").trim();
    return `<p class="eight-cell__value">${esc(quit)}${note ? ` · ${esc(note)}` : ""}</p>`;
  }

  function renderBlock(title, content) {
    return `
        <section class="card eight-block" aria-label="${esc(title)}">
          <span class="overline">${esc(title)}</span>
          ${content}
        </section>`;
  }

  /** 结构位置 tab：D17 八格网格 + 附加区块 + 市场侧灰置提示。 */
  function renderStructuralTab(sp) {
    const s = sp || {};
    const cells = [
      { key: "cash_buffer", label: "现金流缓冲" },
      { key: "stage", label: "身份/阶段约束" },
      { key: "city_constraints", label: "城市约束" },
      { key: "family_duty", label: "家庭责任" },
      { key: "support_network", label: "支持网络" },
      { key: "economic_independence", label: "经济独立" },
      { key: "family_payback", label: "家庭反哺" },
      { key: "reservation_wage", label: "定价底牌" },
    ];
    const grid = cells
      .map(({ key, label }) => {
        const value = fmtValue(s[key]);
        return `
          <div class="card eight-cell">
            <span class="overline">${esc(label)}</span>
            ${value
              ? `<p class="eight-cell__value">${value}</p>`
              : `<p class="eight-cell__value eight-cell__empty">未填写</p>`}
          </div>`;
      })
      .join("");

    const extras = [];
    if (s.exploitation_redlines) extras.push(renderBlock("剥削敏感带", renderRedlines(s.exploitation_redlines)));
    if (s.reproduction_costs) extras.push(renderBlock("再生产账单", renderReproduction(s.reproduction_costs)));
    if (s.mobility) extras.push(renderBlock("流动性与时点", renderMobility(s.mobility)));
    const extrasHtml = extras.length
      ? `<div class="structural__extras">${extras.join("")}</div>`
      : "";

    const marketHtml = Object.prototype.hasOwnProperty.call(s, "market_assessment")
      ? `<div class="eight-market" role="note">市场侧评估 · 待岗位数据积累后启用（D17：市场侧由系统从岗位数据估，用户只填自己那半）</div>`
      : "";

    return `
        <div class="structural">
          <div class="eight-grid">${grid}</div>
          ${extrasHtml}
          ${marketHtml}
        </div>`;
  }

  /** 简历校对：抽取文本 vs 原文 对照，逐项可确认。 */
  function renderResumeReview(rr) {
    if (!rr || typeof rr !== "object") {
      return `<p class="pool-empty" role="status">未上传简历——上传后在这里校对抽取结果。</p>`;
    }
    const items = Array.isArray(rr.items) ? rr.items : [];
    const rows = items
      .map((item) => {
        const label = (item && item.label) || (item && item.field) || "字段";
        const original = String((item && item.original) || "");
        const extracted = String((item && item.extracted) || "");
        return `
        <div class="diff-row" data-field="${esc(item.field || "")}">
          <div class="diff-row__label">${esc(label)}</div>
          <div class="diff-row__cols">
            <div class="diff-cell diff-cell--orig">
              <span class="diff-cell__tag">原文</span>
              <p>${esc(original) || `<span class="eight-cell__empty">—</span>`}</p>
            </div>
            <div class="diff-cell diff-cell--extract">
              <span class="diff-cell__tag">抽取</span>
              <p>${esc(extracted) || `<span class="eight-cell__empty">—</span>`}</p>
            </div>
          </div>
          <button class="btn btn--primary btn--sm" type="button" data-action="review-confirm"
                  aria-label="确认字段：${esc(label)}">确认</button>
        </div>`;
      })
      .join("");
    return `
        <section class="resume-review" aria-label="简历校对">
          <header class="resume-review__head">
            <span class="overline">简历校对</span>
            ${rr.file ? `<span class="resume-review__file">${esc(rr.file)}</span>` : ""}
          </header>
          ${rows || `<p class="pool-empty" role="status">没有可校对的字段。</p>`}
        </section>`;
  }

  /* ---------- DOM 挂载与交互 ---------- */
  function getHost() {
    return document.getElementById("profile");
  }

  let partialPromise = null;
  function mountPartial() {
    if (partialPromise) return partialPromise;
    partialPromise = (async () => {
      const host = getHost();
      if (!host || host.querySelector(".profile-layout")) return;
      try {
        const res = await fetch("partials/profile.html");
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

  function localProfile() {
    return { ...LOCAL_FIXTURE_PROFILE, resume_review: LOCAL_FIXTURE_RESUME_REVIEW };
  }

  async function loadProfile() {
    if (state.loaded) {
      renderAll();
      return;
    }
    state.loaded = true;

    if (typeof TalentForgeApi === "undefined" || TalentForgeApi.USE_FIXTURES) {
      state.profile = localProfile();
      renderAll();
      return;
    }

    try {
      const data = await TalentForgeApi.getProfile();
      state.profile = (data && typeof data === "object") ? data : {};
    } catch (err) {
      state.profile = {};
    }
    renderAll();
  }

  function setPanel(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function renderHead(p) {
    const nameEl = document.getElementById("profile-name");
    const identityEl = document.getElementById("profile-identity");
    if (nameEl) nameEl.textContent = String(p.name || "我的画像");
    if (identityEl) {
      const identity = (p.narrative && p.narrative.identity) || "";
      identityEl.textContent = identity || "一句话叙事待补充";
    }
  }

  function renderAll() {
    const p = state.profile || {};
    renderHead(p);
    setPanel("panel-pool", renderPoolTab(p.narrative_claims));
    setPanel("panel-narrative", renderNarrativeTab(p.narrative));
    setPanel("panel-utility", renderUtilityTab(p.utility_preferences));
    setPanel("panel-structural", renderStructuralTab(p.structural_position));
    setPanel("profile-resume", renderResumeReview(p.resume_review));
    updatePendingCount();
  }

  function updatePendingCount() {
    const n = countTrialClaims((state.profile && state.profile.narrative_claims) || []);
    const badge = document.getElementById("pending-count");
    if (badge) badge.textContent = `待定池 ${n}`;
    const tabBtn = document.getElementById("tab-pool");
    if (tabBtn) tabBtn.textContent = n ? `待定池 (${n})` : "待定池";
  }

  function findClaim(claimId) {
    const claims = (state.profile && state.profile.narrative_claims) || [];
    return claims.find((c) => c && c.claim_id === claimId) || null;
  }

  async function actionClaim(cardEl, action) {
    const claimId = cardEl.dataset.claimId;
    const ok = action === "confirm";
    const nextState = ok ? "active" : "archived";
    const claim = findClaim(claimId);
    if (claim) {
      claim.state = nextState;
      if (ok) claim.evidence_count = (Number(claim.evidence_count) || 0) + 1;
    }
    setPanel("panel-pool", renderPoolTab((state.profile && state.profile.narrative_claims) || []));
    updatePendingCount();

    if (typeof TalentForgeApi !== "undefined" && !TalentForgeApi.USE_FIXTURES) {
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

  function confirmReview(btn) {
    const row = btn.closest("[data-field]");
    if (!row) return;
    const note = document.createElement("span");
    note.className = "resume-review__done";
    note.textContent = "已确认";
    btn.replaceWith(note);
    row.classList.add("is-confirmed");
  }

  function downloadJson(data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "talentforge-profile.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  async function exportProfile() {
    let data = state.profile || {};
    if (typeof TalentForgeApi !== "undefined" && !TalentForgeApi.USE_FIXTURES) {
      try {
        data = await TalentForgeApi.request("/profile/export");
      } catch (err) {
        /* 导出端点失败：回退到当前已加载数据 */
      }
    }
    downloadJson(data);
  }

  function switchTab(tabName) {
    state.activeTab = tabName;
    document.querySelectorAll(".profile-tab").forEach((btn) => {
      const active = btn.dataset.tab === tabName;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", String(active));
    });
    const panels = ["pool", "narrative", "utility", "structural"];
    panels.forEach((name) => {
      const el = document.getElementById(`panel-${name}`);
      if (el) el.hidden = name !== tabName;
    });
  }

  function onHostClick(evt) {
    const exportBtn = evt.target.closest("#profile-export");
    if (exportBtn) {
      evt.preventDefault();
      exportProfile();
      return;
    }
    const tabBtn = evt.target.closest("[data-tab]");
    if (tabBtn) {
      evt.preventDefault();
      switchTab(tabBtn.dataset.tab);
      return;
    }
    const confirmBtn = evt.target.closest("[data-action='claim-confirm']");
    if (confirmBtn) {
      evt.preventDefault();
      actionClaim(confirmBtn.closest("[data-claim-id]"), "confirm");
      return;
    }
    const rejectBtn = evt.target.closest("[data-action='claim-reject']");
    if (rejectBtn) {
      evt.preventDefault();
      actionClaim(rejectBtn.closest("[data-claim-id]"), "reject");
      return;
    }
    const reviewBtn = evt.target.closest("[data-action='review-confirm']");
    if (reviewBtn) {
      evt.preventDefault();
      confirmReview(reviewBtn);
    }
  }

  function onHostKeydown(evt) {
    if (evt.key !== "ArrowLeft" && evt.key !== "ArrowRight") return;
    const tabBtn = evt.target.closest("[data-tab]");
    if (!tabBtn) return;
    evt.preventDefault();
    const tabs = Array.from(document.querySelectorAll(".profile-tab"));
    const idx = tabs.indexOf(tabBtn);
    const dir = evt.key === "ArrowRight" ? 1 : -1;
    const target = tabs[(idx + dir + tabs.length) % tabs.length];
    switchTab(target.dataset.tab);
    target.focus();
  }

  function wireEvents() {
    const host = getHost();
    if (host) {
      host.addEventListener("click", onHostClick);
      host.addEventListener("keydown", onHostKeydown);
    }
  }

  function onEnterProfile() {
    mountPartial().then(loadProfile);
  }

  function init() {
    if (window.TalentForgeRouter && typeof window.TalentForgeRouter.onView === "function") {
      window.TalentForgeRouter.onView("profile", onEnterProfile);
    } else {
      window.addEventListener("route:change", (evt) => {
        if (evt.detail && evt.detail.view === "profile") onEnterProfile();
      });
    }
    if (window.TalentForgeRouter && window.TalentForgeRouter.currentPath() === "/profile") {
      onEnterProfile();
    }
  }

  return {
    ATTR_LABEL,
    LOCAL_FIXTURE_PROFILE,
    LOCAL_FIXTURE_RESUME_REVIEW,
    POOL_EMPTY,
    clip,
    countTrialClaims,
    esc,
    fmtAt,
    fmtValue,
    renderClaimCard,
    renderEvidenceChain,
    renderNarrativeTab,
    renderPoolTab,
    renderResumeReview,
    renderStructuralTab,
    renderUtilityTab,
    init,
  };
})();

if (typeof window !== "undefined") {
  window.TalentForgeProfile = TalentForgeProfile;
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => TalentForgeProfile.init());
  } else {
    TalentForgeProfile.init();
  }
}
