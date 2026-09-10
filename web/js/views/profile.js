/* =========================================================
   TalentForge 画像面板视图（#profile）
   - 四 tab（待确认/叙事/效用/结构位置）：tablist/tab/tabpanel
     ARIA 模式（DESIGN.md §7），纯前端切换，与路由无关
   - 待确认：narrative_claims 中 trial 态渲染 ClaimCard（结构
     同 chat.js：status-pill--trial + 置信 + 证据数 + EvidenceChain
     details + 确认/驳回按钮）；confirm→active（evidence_count+1）、
     reject→archived，fixtures 模式本地乐观更新 + 更新顶部待确认
     计数，真模式调端点；active/archived 进折叠区
   - 叙事轨：identity（衬线大字引言）+ values（标签 pill 组）
     + deep_drives（列表）
    - 效用轨：utility_preferences 逐条渲染（attribute + ordering
      排序，如 薪资：40万以上 > 30-40万 > 20-30万；evidence 非空时
      追加小字"（含 N 次决策回流）"，M4 反馈闭环）
   - 结构位置：D17 八格卡片网格（2 列，>1024px 3 列）+ 工作底线
     /生活成本/退路区块；market_assessment 存在即标注"待数据积累"
     （D17 市场侧灰置，用户只填自己那半）
    - 简历校对：profile.resume_review 存在则渲染 抽取 vs 原文 diff
      视图（逐项确认）；fixtures 模式 mock 示例区块；否则"未上传简历"
    - 作品主张区（M5 §1.3/§5，待确认区上方独立 section#work-section）：
      拉 /api/work/artifacts 渲染作品卡（grade 徽章 strong=active/
      normal=trial/weak=archived 复用 + facts 摘要 + grade_reasons +
      外链 + 入画像/驳回）；fixtures 模式用 LOCAL_WORK_FIXTURES；
      入画像 POST /api/work/claims、驳回 POST /api/work/dismiss
    - 导出 JSON：fixtures 模式本地 Blob 下载；真模式 GET /profile/export
   - 顶部待确认计数：与 chat.js 同计算（profile.narrative_claims 中
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
    work: "作品",
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

  /* 作品主张本地示例（M5）：镜像 /api/work/artifacts 返回结构，fixtures 模式用 */
  const LOCAL_WORK_FIXTURES = {
    artifacts: [
      {
        artifact_id: "github:demo/raft-viewer",
        platform: "github",
        kind: "repo",
        title: "raft-viewer",
        url: "https://github.com/demo/raft-viewer",
        facts: { language: "Python", commits: 142, stars: 87, span_days: 420, is_fork: false },
        grade: "strong",
        grade_reasons: ["R3: 持续 commit ≥ 6 个月，长期投入难伪造"],
        fetched_at: "2026-08-23T08:00:00+00:00",
      },
      {
        artifact_id: "arxiv:2601.01234",
        platform: "arxiv",
        kind: "paper",
        title: "A Note on Consensus Protocols",
        url: "https://arxiv.org/abs/2601.01234",
        facts: {
          authors: ["Zhang San", "Li Si"],
          first_author: "Zhang San",
          year: 2026,
          venue: "arXiv（preprint）",
        },
        grade: "normal",
        grade_reasons: ["R5: preprint 无同行评审，信号上限 normal"],
        fetched_at: "2026-08-23T08:00:00+00:00",
      },
    ],
    dismissed: [],
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

  <section class="work-section" id="work-section" aria-label="作品主张"></section>

  <div class="profile-tabs" id="profile-tabs" role="tablist" aria-label="画像区块">
    <button class="profile-tab is-active" type="button" role="tab" id="tab-pool" aria-selected="true" aria-controls="panel-pool" data-tab="pool">待确认</button>
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
    work: { artifacts: [], dismissed: [], claimedIds: new Set() },
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

  /** 待确认计数：profile.narrative_claims 中 trial 态主张数（同 chat.js 语义）。 */
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

  /** 待确认 tab：trial 列表 + active/archived 折叠区。 */
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

  /** 工作底线：每条 stance 语义化（never → 硬边界不可妥协）。 */
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
      { key: "reservation_wage", label: "最低可接受薪资" },
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
    if (s.exploitation_redlines) extras.push(renderBlock("工作底线", renderRedlines(s.exploitation_redlines)));
    if (s.reproduction_costs) extras.push(renderBlock("生活成本", renderReproduction(s.reproduction_costs)));
    if (s.mobility) extras.push(renderBlock("退路与时机", renderMobility(s.mobility)));
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

  /* ---------- 作品主张区（M5 spec §1.3/§5） ---------- */

  const WORK_GRADE_LABEL = { strong: "强", normal: "普通", weak: "弱" };
  /* grade → 复用 status-pill 语义色：强=ok 绿 / 普通=琥珀 hold / 弱=中性灰 */
  const WORK_GRADE_PILL = {
    strong: "status-pill status-pill--active",
    normal: "status-pill status-pill--trial",
    weak: "status-pill status-pill--archived",
  };
  const WORK_PLATFORM_LABEL = { github: "GitHub", gitee: "Gitee", arxiv: "arXiv" };
  const WORK_KIND_LABEL = { repo: "仓库", paper: "论文" };
  /* 内容探针类型中文映射（D29）：facts.content_probe.content_type → 展示名 */
  const PROBE_TYPE_LABEL = {
    engineering: "工程实现",
    research: "研究项目",
    documentation: "资料收集",
    coursework: "课程作业",
    mixed: "混合",
  };
  const WORK_EMPTY = "还没有可校对的作品——去平台源页输入 GitHub/Gitee 用户名或 arXiv 作者名拉取";

  function workGradePill(grade) {
    return WORK_GRADE_PILL[grade] || WORK_GRADE_PILL.normal;
  }

  /** 外链安全化：仅放行 http(s)，其余回退 #（防 javascript: 注入进 href）。 */
  function safeWorkUrl(url) {
    const s = String(url ?? "").trim();
    return /^https?:\/\//i.test(s) ? esc(s) : "#";
  }

  /** facts 摘要：repo = 语言·commits·stars；paper = 年份·一作/合作者·venue。 */
  function workFactsSummary(artifact) {
    const facts = (artifact && artifact.facts) || {};
    if (artifact && artifact.kind === "paper") {
      const authors = Array.isArray(facts.authors) ? facts.authors.map((a) => String(a)) : [];
      const isFirst = authors.length > 0 && String(facts.first_author || "") === authors[0];
      return [
        facts.year != null && facts.year !== "" ? String(facts.year) : "",
        authors.length ? (isFirst ? "一作" : "合作者") : "",
        facts.venue != null && facts.venue !== "" ? String(facts.venue) : "",
      ].filter(Boolean);
    }
    return [
      facts.language != null && facts.language !== "" ? String(facts.language) : "",
      facts.commits != null ? `${facts.commits} commits` : "",
      facts.stars != null ? `${facts.stars} stars` : "",
    ].filter(Boolean);
  }

  /** 内容探针小字行（D29）：facts.content_probe → "探针：{类型中文}·{summary}"。 */
  function workProbeLine(facts) {
    const probe = facts && typeof facts.content_probe === "object" ? facts.content_probe : null;
    if (!probe) return "";
    const label = PROBE_TYPE_LABEL[probe.content_type] || String(probe.content_type || "");
    const summary = String(probe.summary || "").trim();
    return `<p class="work-card__probe">探针：${esc(label)}${summary ? `·${esc(summary)}` : ""}</p>`;
  }

  /** 单条作品卡：grade 徽章 + 标题外链 + facts 摘要 + grade_reasons + 入画像/驳回。 */
  function renderWorkCard(artifact, claimed) {
    if (!artifact || typeof artifact !== "object") return "";
    const id = String(artifact.artifact_id || "");
    const grade = WORK_GRADE_LABEL[artifact.grade] ? artifact.grade : "normal";
    const platform = WORK_PLATFORM_LABEL[artifact.platform] || String(artifact.platform || "");
    const kindLabel = WORK_KIND_LABEL[artifact.kind] || String(artifact.kind || "");
    const factsHtml = workFactsSummary(artifact).map(esc).join(" · ");
    const reasonsHtml = (Array.isArray(artifact.grade_reasons) ? artifact.grade_reasons : [])
      .map((r) => esc(String(r)))
      .join("；");
    const claimCtl = claimed
      ? `<span class="status-pill status-pill--active">已入画像</span>`
      : `<button class="btn btn--primary btn--sm" type="button" data-action="work-claim" data-id="${esc(id)}"
                 aria-label="作品入画像：${esc(clip(artifact.title, 20))}">入画像</button>`;
    return `
        <article class="card card--embedded work-card" data-artifact-id="${esc(id)}" role="listitem">
          <header class="work-card__head">
            <span class="${workGradePill(grade)}">${esc(WORK_GRADE_LABEL[grade])}</span>
            <a class="work-card__title" href="${safeWorkUrl(artifact.url)}" target="_blank"
               rel="noopener noreferrer">${esc(artifact.title || id)} ↗</a>
            <span class="work-card__meta">${esc(platform)}${kindLabel ? ` · ${esc(kindLabel)}` : ""}</span>
          </header>
          ${factsHtml ? `<p class="work-card__facts">${factsHtml}</p>` : ""}
          ${workProbeLine(artifact.facts)}
          ${reasonsHtml ? `<p class="work-card__reasons">${reasonsHtml}</p>` : ""}
          <footer class="work-card__actions">
            ${claimCtl}
            <button class="btn btn--ghost btn--sm" type="button" data-action="work-dismiss" data-id="${esc(id)}"
                    aria-label="驳回作品：${esc(clip(artifact.title, 20))}">驳回</button>
          </footer>
        </article>`;
  }

  /** 作品主张区块（待确认 tab 上方独立 section#work-section 的内容）。 */
  function renderWorkSection(artifacts, dismissed, claimed) {
    const list = Array.isArray(artifacts) ? artifacts : [];
    const dismissedSet = new Set(Array.isArray(dismissed) ? dismissed : []);
    const claimedSet = new Set(claimed || []);
    const visible = list.filter((a) => a && !dismissedSet.has(a.artifact_id));
    const cards = visible
      .map((a) => renderWorkCard(a, claimedSet.has(a.artifact_id)))
      .join("");
    return `
        <header class="work-section__head">
          <span class="overline">作品主张</span>
          <span class="work-section__count">${visible.length} 条 · 公开可验证，校对后写入画像</span>
        </header>
        ${visible.length
          ? `<div class="work-section__list" role="list" aria-label="作品主张列表">${cards}</div>`
          : `<p class="pool-empty" role="status">${esc(WORK_EMPTY)}</p>`}`;
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
    renderWork();
    updatePendingCount();
  }

  /* ---------- 作品主张区交互（M5） ---------- */

  function renderWork() {
    setPanel("work-section", renderWorkSection(
      state.work.artifacts,
      state.work.dismissed,
      claimedWorkIds(),
    ));
  }

  /** 已入集合 = 本会话已主张的 id ∪ 画像 narrative_claims 中 sources kind=work 的 ref。 */
  function claimedWorkIds() {
    const ids = new Set(state.work.claimedIds || []);
    for (const claim of (state.profile && state.profile.narrative_claims) || []) {
      for (const src of (claim && claim.sources) || []) {
        if (src && src.kind === "work" && src.ref) ids.add(String(src.ref));
      }
    }
    return ids;
  }

  async function workRequest(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /* 作品加载：真模式每次进入视图直连后端（no-store，sources 页可能新拉了作品）；
     fixtures 模式用 LOCAL_WORK_FIXTURES；作品拉取无 fixtures 假数据。 */
  async function loadWork() {
    if (typeof TalentForgeApi === "undefined" || TalentForgeApi.USE_FIXTURES) {
      state.work = {
        artifacts: LOCAL_WORK_FIXTURES.artifacts,
        dismissed: [...LOCAL_WORK_FIXTURES.dismissed],
        claimedIds: new Set(),
      };
      renderWork();
      return;
    }
    try {
      const res = await fetch("/api/work/artifacts", {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.work = {
        artifacts: Array.isArray(data && data.artifacts) ? data.artifacts : [],
        dismissed: Array.isArray(data && data.dismissed) ? data.dismissed : [],
        claimedIds: new Set(),
      };
    } catch (err) {
      state.work = { artifacts: [], dismissed: [], claimedIds: new Set() };
    }
    renderWork();
  }

  async function claimWorkArtifact(artifactId, btn) {
    if (!artifactId) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "写入中…";
    }
    /* fixtures 模式本地乐观；真模式端点成功后才置"已入画像" */
    if (typeof TalentForgeApi !== "undefined" && !TalentForgeApi.USE_FIXTURES) {
      try {
        await workRequest("/api/work/claims", { artifact_ids: [artifactId] });
      } catch (err) {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "入画像";
        }
        return;
      }
    }
    state.work.claimedIds.add(artifactId);
    renderWork();
  }

  async function dismissWorkArtifact(artifactId) {
    if (!artifactId) return;
    if (typeof TalentForgeApi !== "undefined" && !TalentForgeApi.USE_FIXTURES) {
      try {
        await workRequest("/api/work/dismiss", { artifact_id: artifactId });
      } catch (err) {
        return;
      }
    }
    state.work.dismissed.push(artifactId);
    renderWork();
  }

  function updatePendingCount() {
    const n = countTrialClaims((state.profile && state.profile.narrative_claims) || []);
    const badge = document.getElementById("pending-count");
    if (badge) badge.textContent = `待确认 ${n}`;
    const tabBtn = document.getElementById("tab-pool");
    if (tabBtn) tabBtn.textContent = n ? `待确认 (${n})` : "待确认";
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
    const workClaimBtn = evt.target.closest("[data-action='work-claim']");
    if (workClaimBtn) {
      evt.preventDefault();
      claimWorkArtifact(workClaimBtn.dataset.id, workClaimBtn);
      return;
    }
    const workDismissBtn = evt.target.closest("[data-action='work-dismiss']");
    if (workDismissBtn) {
      evt.preventDefault();
      dismissWorkArtifact(workDismissBtn.dataset.id);
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
    mountPartial().then(() => {
      loadProfile();
      loadWork();
    });
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
    FALLBACK_PARTIAL,
    LOCAL_FIXTURE_PROFILE,
    LOCAL_FIXTURE_RESUME_REVIEW,
    LOCAL_WORK_FIXTURES,
    POOL_EMPTY,
    WORK_EMPTY,
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
    renderWorkCard,
    renderWorkSection,
    workFactsSummary,
    workGradePill,
    workProbeLine,
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
