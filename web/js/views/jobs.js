/* =========================================================
   TalentForge 决策工作台视图（#jobs）
   - 岗位列表（VerdictBadge 前置）+ 详情面板双栏（.l-split 2fr/3fr，
     <1024px 折叠为列表在上、详情在下）
   - 列表行 = 可点击卡片（.card--clickable），选中态 .is-active；
     双击行外链打开 JD 原文（target=_blank）
   - 详情面板：VerdictBadge + 完整 meta + 决策理由 + RiskNote 展开区
     （risk_hits 逐条渲染，why 缺省给通用知情文案）+ 理由链 EvidenceChain
     （evidence 为空时隐藏）+ gap/补短板区块 + "聊聊这个岗位"（跳对话页）
   - 筛选：搜索框（q，标题/公司/地点模糊匹配）+ 城市下拉（从数据去重生成）
     + verdict 四态 pill（全部/投/观望/不投）。假数据模式本地过滤；
     真模式调 getJobs({city,verdict,q}) 带参数
   - 生成报告：假数据模式本地 mock（按钮变"报告中…"禁用 → 恢复 + 状态提示）；
     真模式 POST /api/report/run → 轮询 /api/report/status 直到 done → 刷新列表
   - 空态："没有符合筛选的岗位"（有数据但筛选无匹配）/ 引导卡（完全无数据）
   - 数量统计："共 N 个岗位 · 投 M · 观望 K"
    - 跨页联动：监听 window "job:focus" 事件（对话页决策卡点击产生），
      进入工作台时定位对应岗位；"聊聊这个岗位"反向派发 job:focus + 跳 /chat
     - M4 反馈闭环：详情底部"我的行动"行 = 我已投递 / 我跳过了 / 记录结果
       （原地展开 面试中/已拒/offer/无回音）三轻量按钮；已记录态显示徽章
       "已记录：投递 08-22" + "改"回到未记录态。fixtures 模式本地 mock，
       真模式 POST /api/feedback/events（fetch no-store，参照 sources.js）
     - M6 信号投资循环：gap 兼容对象形态 {skill,severity,evidence}（severity
       徽章 major=risk 色 / minor=灰）；gap 非空时"补信号"按钮展开推荐区
       （fixtures 本地示例；真模式 POST /api/suggest/for-job 逐 gap 渲染
       repo 推荐卡，外链新 tab；无 gaps 给"先跑决策"提示；再点收起）
    渲染函数为纯字符串输出（文本一律 esc 转义），DOM 层通过 <template> 解析
    后挂载，便于 node:test 直接断言。
   ========================================================= */

"use strict";

const TalentForgeJobs = (() => {
  /* ---------- 标签映射（DESIGN.md §2 三值语义 / §5 状态） ---------- */
  const VERDICT_LABEL = { apply: "投", hold: "观望", skip: "不投" };
  /* 反馈动作中文（用户真实行为，与系统判定 VERDICT_LABEL 区分，spec §3） */
  const FEEDBACK_VERDICT_LABEL = { apply: "投递", hold: "观望", skip: "跳过" };
  const OUTCOME_LABEL = {
    interview: "面试中",
    rejected: "已拒",
    offer: "offer",
    no_response: "无回音",
  };
  const KIND_LABEL = {
    jd: "JD 原文",
    resume: "简历",
    dialogue: "对话",
    feedback: "反馈",
    behavior: "行为",
    system: "系统",
  };
  /* M6 gap severity 中文（major=risk 色徽章 / minor=灰徽章） */
  const SEVERITY_LABEL = { major: "主要", minor: "次要" };
  /* M9 岗位胜任力：candidate_level → 徽章语义（复用 status-pill 三态配色） */
  const COMPETENCY_LEVEL_LABEL = { strong: "证据充分", partial: "部分证据", missing: "无证据" };
  const COMPETENCY_LEVEL_PILL = {
    strong: "status-pill status-pill--active",
    partial: "status-pill status-pill--trial",
    missing: "status-pill status-pill--archived",
  };
  const SUGGEST_NO_GAPS_HINT = "该岗位暂无 gap 分析——先在对话页跑一次决策";
  const SUGGEST_LOADING_TEXT = "找项目中…";
  const SUGGEST_ERROR_TEXT = "推荐失败：后端未启动";
  /* 风险命中无 why 字段时的通用知情文案（D13 知情非恐吓） */
  const DEFAULT_RISK_WHY =
    "这是你画像里记录的结构性风险点——建议在决定之前，先弄清它对工时、收入与长期成长的实际影响。";
  const EMPTY_FILTER_HINT = "没有符合筛选的岗位";

  /* ---------- 离线假数据：镜像 talentforge/api/fixtures.py get_fixture_jobs ----------
     8 个深圳后端岗位，覆盖 apply/hold/skip 三态 + 含/不含风险。
     与对话 fixture 对应的岗位（星辰科技/云帆信息）补上 evidence，
     用于演示理由链；其余岗位无 evidence 字段 → 详情理由链隐藏。 */
  const LOCAL_FIXTURE_JOBS = [
    {
      title: "数据平台后端工程师",
      company: "观澜数据",
      location: "深圳·福田",
      salary: "30-45K·14薪",
      url: "https://www.zhipin.com/job_detail/data_1006.html",
      verdict: "apply",
      reason: "成长契合高（流计算方向补强），薪资覆盖保留工资，双休弹性工时。",
      risk_hits: [],
      gap: ["Flink 流处理"],
      remediation: ["搭一个 Flink 词频 demo 上简历", "面试前补两道流计算设计题"],
    },
    {
      title: "后端开发工程师（Python/Go）",
      company: "睿达网络",
      location: "深圳·南山",
      salary: "28-45K·15薪",
      url: "https://www.zhipin.com/job_detail/ruida_1010.html",
      verdict: "apply",
      reason: "技术栈双覆盖、分布式业务对口，仅需核实工时与加班口径。",
      risk_hits: [{ key: "弹性工作制需核实", label: "弹性工作制（需核实）" }],
      gap: ["流量治理"],
      remediation: ["整理一个限流/熔断实践案例"],
    },
    {
      title: "Python 后端工程师",
      company: "星辰科技",
      location: "深圳·南山",
      salary: "25-50K·16薪",
      url: "https://www.zhipin.com/job_detail/python_1001.html",
      verdict: "hold",
      reason: "市场契合高，但 JD 明确标注 996，与硬边界冲突——先观望对价能否谈拢。",
      risk_hits: [{ key: "996", label: "996 工作制" }],
      gap: ["K8s 容器编排", "高并发压测"],
      remediation: ["若谈薪资需先确认加班口径", "个人项目补 K8s 部署实践"],
      evidence: [
        { kind: "jd", ref: "python_1001.html", text: "工作时间为 996 工作制" },
        { kind: "dialogue", ref: "turn-1", text: "用户偏好深圳后端岗" },
      ],
    },
    {
      title: "Go 后端开发",
      company: "海天互娱",
      location: "深圳·宝安",
      salary: "20-30K·13薪",
      url: "https://www.zhipin.com/job_detail/go_1007.html",
      verdict: "hold",
      reason: "IM 场景能补高并发经验，但单休安排与偏好冲突，需确认调休补偿。",
      risk_hits: [{ key: "单休", label: "单休工作制" }],
      gap: ["WebSocket 长连接", "消息队列"],
      remediation: ["补一个 IM 聊天 demo 的实时链路", "确认单休是否换算加班费"],
    },
    {
      title: "高级后端开发（Java）",
      company: "云帆信息",
      location: "深圳·南山",
      salary: "15-25K",
      url: "https://www.zhipin.com/job_detail/java_1002.html",
      verdict: "skip",
      reason: "薪资低于保留工资，且含竞业限制条款，与硬边界直接冲突。",
      risk_hits: [{ key: "竞业限制", label: "竞业限制条款" }],
      gap: ["Java 交易系统经验"],
      remediation: ["竞业为硬边界，暂缓投入"],
      evidence: [
        { kind: "jd", ref: "java_1002.html", text: "含竞业限制条款，范围覆盖同业" },
        { kind: "system", ref: "deal-breaker", text: "用户 deal_breakers 含竞业限制" },
      ],
    },
    {
      title: "Golang 基础架构工程师",
      company: "星环科技",
      location: "深圳·南山",
      salary: "30-45K·14薪",
      url: "https://www.zhipin.com/job_detail/golang_1004.html",
      verdict: "skip",
      reason: "明确 996 + 无偿加班，两处硬边界直接命中，薪资不补偿工时。",
      risk_hits: [
        { key: "996", label: "996 工作制" },
        { key: "无偿加班", label: "无偿加班" },
      ],
      gap: ["K8s 源码级理解"],
      remediation: ["决策已跳过，不建议投入时间"],
    },
    {
      title: "后端研发（量化中后台）",
      company: "方舟金融",
      location: "深圳·福田",
      salary: "35-60K·16薪",
      url: "https://www.zhipin.com/job_detail/finance_1008.html",
      verdict: "skip",
      reason: "薪资诱人但含竞业限制条款，与把竞业当硬边界的立场冲突。",
      risk_hits: [{ key: "竞业限制", label: "竞业限制条款" }],
      gap: ["量化领域知识"],
      remediation: ["竞业为硬边界，暂缓投入"],
    },
    {
      title: "Java 后端工程师（外包驻场）",
      company: "微光教育",
      location: "深圳·龙华",
      salary: "12-18K",
      url: "https://www.zhipin.com/job_detail/outsource_1009.html",
      verdict: "skip",
      reason: "无社保 + 加班费模糊，法定义务缺失与低薪双重问题。",
      risk_hits: [
        { key: "无社保", label: "无社会保险" },
        { key: "加班费模糊", label: "加班费规则模糊" },
      ],
      gap: ["——"],
      remediation: ["决策已跳过，不符合底线"],
    },
  ];

  /* ---------- 推荐区离线示例（M6 spec §2.3）：镜像 /api/suggest/for-job results 形态 ---------- */
  const LOCAL_SUGGEST_FIXTURES = [
    {
      skill: "Flink 流处理",
      severity: "major",
      suggestions: [
        {
          full_name: "apache/flink",
          url: "https://github.com/apache/flink",
          stars: 24000,
          description: "流处理与批处理一体化的分布式计算引擎，stateful 计算 exactly-once 语义。",
          language: "Java",
          pushed_at: "2026-08-20T08:30:00Z",
          why: "30 天内有推送、issues 维护得动，适合补流处理实战信号。",
        },
        {
          full_name: "pyflink/pyflink-examples",
          url: "https://github.com/pyflink/pyflink-examples",
          stars: 890,
          description: "PyFlink 官方示例集：wordcount / window / state 与 checkpoint 演示。",
          language: "Python",
          pushed_at: "2026-08-12T10:00:00Z",
          why: "stars 适中、示例即学即用，上手成本低于读引擎源码。",
        },
      ],
    },
    {
      skill: "K8s 容器编排",
      severity: "minor",
      suggestions: [
        {
          full_name: "kubernetes/community",
          url: "https://github.com/kubernetes/community",
          stars: 12000,
          description: "Kubernetes 社区协作文档：SIG 兴趣组、贡献指南与 good first issue 入口。",
          language: "Shell",
          pushed_at: "2026-08-18T06:00:00Z",
          why: "文档 PR 门槛低，是补 K8s 实践信号的最短路径。",
        },
        {
          full_name: "operator-framework/operator-sdk",
          url: "https://github.com/operator-framework/operator-sdk",
          stars: 6500,
          description: "构建 K8s Operator 的 SDK：脚手架生成控制器与 CRD，快速产出可展示项目。",
          language: "Go",
          pushed_at: "2026-08-15T09:00:00Z",
          why: "能做出端到端 Operator demo，直接对应 JD 的容器编排经验。",
        },
      ],
    },
  ];

  /* 兜底骨架：与 web/partials/jobs.html 保持一致（fetch 失败时注入） */
  const FALLBACK_PARTIAL = `
<div class="jobs-layout">
  <div class="jobs-toolbar">
    <input class="input jobs-toolbar__q" id="jobs-q" type="search"
           placeholder="搜索标题/公司/地点…" aria-label="搜索岗位" autocomplete="off" />
    <select class="input jobs-toolbar__city" id="jobs-city" aria-label="按城市筛选"></select>
    <div class="jobs-verdict" id="jobs-verdict" role="group" aria-label="按判定筛选">
      <button class="verdict-filter is-active" type="button" data-verdict-filter="" aria-pressed="true">全部</button>
      <button class="verdict-filter" type="button" data-verdict-filter="apply" aria-pressed="false">投</button>
      <button class="verdict-filter" type="button" data-verdict-filter="hold" aria-pressed="false">观望</button>
      <button class="verdict-filter" type="button" data-verdict-filter="skip" aria-pressed="false">不投</button>
    </div>
    <button class="btn btn--primary" id="jobs-report" type="button">生成报告</button>
  </div>
  <p class="jobs-status" id="jobs-status" role="status" aria-live="polite" hidden></p>
  <p class="jobs-count" id="jobs-count" aria-label="岗位统计"></p>
  <div class="l-split jobs-split">
    <section class="jobs-list" id="jobs-list" role="list" aria-label="岗位列表"></section>
    <section class="jobs-detail" id="jobs-detail" role="region" aria-label="岗位详情"></section>
  </div>
</div>`;

  /* ---------- 视图状态 ---------- */
  const state = {
    loaded: false,
    jobs: [],
    cities: [],
    filters: { q: "", city: "", verdict: "" },
    selectedUrl: "",
    pendingFocus: null,
    reporting: false,
    feedback: {}, /* {[job.url]: {verdict, outcome, at}} */
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

  /** 反馈徽章日期 MM-DD（Date 或 ISO 兼容，本地时区）。 */
  function fmtDay(value) {
    if (!value) return "";
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    const pad = (x) => String(x).padStart(2, "0");
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /** ISO 时间取 YYYY-MM-DD 段（非 ISO / 空给空串）。 */
  function fmtIsoDay(iso) {
    const m = /^\d{4}-\d{2}-\d{2}/.exec(String(iso || ""));
    return m ? m[0] : "";
  }

  /** gap 归一：字符串（旧 fixtures）与对象（{skill,severity,evidence}）混合数组，
      剔除空串 / "——" 占位 / 无 skill 项。 */
  function normalizeGaps(gap) {
    const list = Array.isArray(gap) ? gap : [];
    return list.filter((g) => {
      if (g == null) return false;
      if (typeof g === "string") return g.trim() !== "" && g !== "——";
      if (typeof g === "object") return String(g.skill || "").trim() !== "";
      return false;
    });
  }

  function htmlToElement(html) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html.trim();
    return tpl.content.firstElementChild;
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  /* ---------- 纯筛选/统计函数（测试可直接断言） ---------- */

  /** 组合过滤：q（标题/公司/地点/薪资模糊匹配）+ city + verdict。 */
  function filterJobs(jobs, filters = {}) {
    const q = String(filters.q || "").trim().toLowerCase();
    const city = String(filters.city || "").trim();
    const verdict = String(filters.verdict || "").trim();
    return (jobs || []).filter((job) => {
      if (verdict && job.verdict !== verdict) return false;
      if (city && job.location !== city) return false;
      if (q) {
        const hay = [job.title, job.company, job.location, job.salary].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  /** 从数据去重生成城市下拉选项（按中文排序，保证稳定顺序）。 */
  function collectCities(jobs) {
    const seen = new Set();
    const cities = [];
    for (const job of jobs || []) {
      const city = String((job && job.location) || "").trim();
      if (city && !seen.has(city)) {
        seen.add(city);
        cities.push(city);
      }
    }
    return cities.sort((a, b) => a.localeCompare(b, "zh"));
  }

  /** 判定数量统计：total / apply / hold / skip。 */
  function countStats(jobs) {
    const stats = { total: 0, apply: 0, hold: 0, skip: 0 };
    for (const job of jobs || []) {
      stats.total += 1;
      if (job.verdict === "apply") stats.apply += 1;
      else if (job.verdict === "hold") stats.hold += 1;
      else if (job.verdict === "skip") stats.skip += 1;
    }
    return stats;
  }

  /* ---------- 纯渲染函数（测试可直接断言） ---------- */

  function renderVerdictBadge(verdict) {
    const label = VERDICT_LABEL[verdict] || verdict || "";
    return `<span class="verdict-badge verdict-badge--${esc(verdict)}">${esc(label)}</span>`;
  }

  function renderRiskTag(hit) {
    const label = (hit && hit.label) || (hit && hit.key) || "风险";
    return `<span class="risk-tag">风险 · ${esc(label)}</span>`;
  }

  function renderRiskNote(hit) {
    const label = (hit && hit.label) || (hit && hit.key) || "风险";
    const why = (hit && hit.why) || DEFAULT_RISK_WHY;
    return `
        <aside class="risk-note">
          <div class="risk-note__label">风险 · ${esc(label)}</div>
          <details>
            <summary class="risk-note__summary">为什么是风险</summary>
            <p class="risk-note__why">${esc(why)}</p>
          </details>
        </aside>`;
  }

  function renderEvidenceChain(items, { label } = {}) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return "";
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

  function renderJobRow(job, { selected } = {}) {
    const verdict = VERDICT_LABEL[job.verdict] || job.verdict;
    const meta = [job.company, job.location, job.salary].filter(Boolean).join(" · ");
    const risks = Array.isArray(job.risk_hits) ? job.risk_hits : [];
    const riskTags = risks.length
      ? `<div class="risk-tags">${risks.map(renderRiskTag).join("")}</div>`
      : "";
    return `
        <article class="card card--clickable job-row${selected ? " is-active" : ""}"
                 data-job-url="${esc(job.url)}" role="button" tabindex="0"
                 aria-label="查看岗位：${esc(job.title || "")}（${esc(verdict)}）"
                 ${selected ? 'aria-current="true"' : ""}>
          <header class="job-row__head">
            ${renderVerdictBadge(job.verdict)}
            <h3 class="job-row__title">${esc(job.title)}</h3>
          </header>
          <p class="card__meta">${esc(meta)}</p>
          ${riskTags}
        </article>`;
  }

  /** 列表 HTML；空列表（有数据但筛选无匹配）时输出空态提示。 */
  function renderJobList(jobs, { selectedUrl } = {}) {
    const list = Array.isArray(jobs) ? jobs : [];
    if (!list.length) {
      return `<p class="jobs-empty" role="status">${esc(EMPTY_FILTER_HINT)}</p>`;
    }
    return list
      .map((job) => renderJobRow(job, { selected: selectedUrl != null && job.url === selectedUrl }))
      .join("");
  }

  /** 岗位胜任力折叠区（M9）：6 维 × 画像证据强度徽章 + 证据引用/缺口说明。 */
  function renderCompetencyBlock(job) {
    const competency = Array.isArray(job.competency) ? job.competency : [];
    if (!competency.length) return "";
    const rows = competency.map(renderCompetencyRow).join("");
    return `
        <details class="job-detail__section job-detail__competency">
          <summary class="job-detail__sub job-detail__competency-summary">岗位胜任力模型（${competency.length} 维）</summary>
          <div class="job-detail__competency-list">
            ${rows}
          </div>
        </details>`;
  }

  /** 单维：维度名 + 强度徽章 + 证据引用/缺口说明。 */
  function renderCompetencyRow(assessment) {
    const level = String((assessment && assessment.candidate_level) || "missing");
    const levelPill = COMPETENCY_LEVEL_PILL[level] || COMPETENCY_LEVEL_PILL.missing;
    const levelLabel = COMPETENCY_LEVEL_LABEL[level] || "无证据";
    const refs = Array.isArray(assessment && assessment.evidence_refs)
      ? assessment.evidence_refs.map((r) => `<li>${esc(clip(String(r), 60))}</li>`).join("")
      : "";
    const gapNote = String((assessment && assessment.gap_note) || "").trim();
    return `
        <div class="competency-row">
          <div class="competency-row__head">
            <strong class="competency-row__dimension">${esc(assessment && assessment.dimension)}</strong>
            <span class="${levelPill}">${esc(levelLabel)}</span>
          </div>
          ${refs ? `<ul class="competency-row__refs">${refs}</ul>` : ""}
          ${gapNote && level !== "strong"
            ? `<p class="competency-row__gap">${esc(clip(gapNote, 120))}</p>` : ""}
        </div>`;
  }

  /** 单条 gap：字符串 → 旧 <li> 形态；对象 → skill 粗体 + severity 徽章 + evidence 小字。 */
  function renderGapItem(gap) {
    if (gap != null && typeof gap === "object") {
      const sev = String(gap.severity || "").trim();
      const sevBadge = SEVERITY_LABEL[sev]
        ? `<span class="gap-sev gap-sev--${esc(sev)}">${esc(SEVERITY_LABEL[sev])}</span>`
        : "";
      const evidence = String(gap.evidence || "").trim();
      return `
            <li class="gap-item">
              <span class="gap-item__head">
                <strong class="gap-item__skill">${esc(gap.skill)}</strong>
                ${sevBadge}
              </span>
              ${evidence ? `<span class="gap-item__evidence">${esc(evidence)}</span>` : ""}
            </li>`;
    }
    return `<li>${esc(gap)}</li>`;
  }

  /** gap/补短板区块：能力差距（双形态兼容）+ 建议动作；
      gap 非空时附"补信号"按钮 + 推荐区容器（默认隐藏，点击按钮填充）。 */
  function renderGapBlock(job) {
    const gaps = normalizeGaps(job.gap);
    const remediation = Array.isArray(job.remediation) ? job.remediation : [];
    const gapItems = gaps.map(renderGapItem).join("");
    const remItems = remediation.map((r) => `<li>${esc(r)}</li>`).join("");
    const suggestToggle = gaps.length ? `
          <div class="job-detail__suggest-toggle">
            <button class="btn btn--ghost btn--sm" type="button" data-action="suggest-toggle"
                    data-job-url="${esc(job.url)}" aria-expanded="false" aria-controls="jobs-suggest-box"
                    aria-label="为该岗位的能力差距推荐补信号项目：${esc(job.title || "")}">补信号</button>
          </div>
          <div class="suggest-box" id="jobs-suggest-box" data-role="suggest-box" hidden></div>` : "";
    return `
        <section class="job-detail__section job-detail__gaps" aria-label="补短板建议">
          <span class="overline">补短板</span>
          <div class="job-detail__gaps-block">
            <h4 class="job-detail__sub">能力差距</h4>
            <ul class="job-detail__gaps-list">${gapItems}</ul>
          </div>
          ${remItems ? `
          <div class="job-detail__gaps-block">
            <h4 class="job-detail__sub">建议动作</h4>
            <ul class="job-detail__gaps-list">${remItems}</ul>
          </div>` : ""}
          ${suggestToggle}
        </section>`;
  }

  /** 推荐区状态行（加载 / 失败 / 无 gap 提示）。 */
  function renderSuggestHint(text, tone = "") {
    const cls = tone ? ` suggest-box__hint--${tone}` : "";
    return `<p class="suggest-box__hint${cls}">${esc(text)}</p>`;
  }

  /** 推荐卡（单 repo）：stars / 描述截断 80 / language · pushed 日期 / why 小字 / 外链"参与"。 */
  function renderSuggestCard(item) {
    const s = item || {};
    const desc = clip(s.description, 80);
    const meta = [s.language, fmtIsoDay(s.pushed_at)].filter(Boolean).join(" · ");
    return `
            <li class="suggest-card">
              <div class="suggest-card__head">
                <a class="suggest-card__name" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.full_name)}</a>
                <span class="suggest-card__stars">★ ${esc(s.stars ?? 0)}</span>
              </div>
              ${desc ? `<p class="suggest-card__desc">${esc(desc)}</p>` : ""}
              ${meta ? `<p class="suggest-card__meta">${esc(meta)}</p>` : ""}
              ${s.why ? `<p class="suggest-card__why">${esc(s.why)}</p>` : ""}
              <a class="suggest-card__link" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">参与 ↗</a>
            </li>`;
  }

  /** 推荐区主体（补信号展开内容）：逐 gap 组渲染建议卡。
      入参兼容 for-job 响应（{results} / {gaps: []}）与纯数组；空 → 无 gap 提示。 */
  function renderSuggestBox(data) {
    const groups = Array.isArray(data) ? data
      : Array.isArray(data && data.results) ? data.results
      : [];
    if (!groups.length) {
      return renderSuggestHint(SUGGEST_NO_GAPS_HINT);
    }
    return groups.map((group) => {
      const g = group || {};
      const cards = (Array.isArray(g.suggestions) ? g.suggestions : []).map(renderSuggestCard).join("");
      return `
        <section class="suggest-group">
          <h4 class="suggest-group__skill">${esc(g.skill)}</h4>
          ${cards || renderSuggestHint("该方向暂无推荐")}
        </section>`;
    }).join("");
  }

  /** 反馈行（M4 spec §3）：未记录态 = 三轻量按钮 + 默认隐藏 outcome 组；已记录态 = 徽章 + 改。 */
  function renderFeedbackRow(job, feedback) {
    const title = (job && job.title) || "";
    if (feedback && feedback.verdict) {
      const label = FEEDBACK_VERDICT_LABEL[feedback.verdict] || feedback.verdict;
      return `
          <div class="feedback-row feedback-row--done">
            <span class="overline feedback-row__label">我的行动</span>
            <span class="status-pill status-pill--active">已记录：${esc(label)} ${esc(fmtDay(feedback.at))}</span>
            <button class="btn btn--ghost btn--sm" type="button" data-action="feedback-edit"
                    aria-label="修改反馈记录：${esc(title)}">改</button>
          </div>`;
    }
    const outcomeBtns = Object.entries(OUTCOME_LABEL).map(([key, label]) => `
            <button class="btn btn--ghost btn--sm" type="button"
                    data-action="feedback-outcome" data-outcome="${esc(key)}"
                    aria-label="记录结果：${esc(label)}（${esc(title)}）">${esc(label)}</button>`).join("");
    return `
        <div class="feedback-row">
          <span class="overline feedback-row__label">我的行动</span>
          <div class="feedback-row__actions">
            <button class="btn btn--ghost btn--sm" type="button"
                    data-action="feedback-decided" data-verdict="apply"
                    aria-label="记录我的行动：已投递（${esc(title)}）">我已投递</button>
            <button class="btn btn--ghost btn--sm" type="button"
                    data-action="feedback-decided" data-verdict="skip"
                    aria-label="记录我的行动：跳过（${esc(title)}）">我跳过了</button>
            <button class="btn btn--ghost btn--sm" type="button"
                    data-action="feedback-outcome-toggle" aria-expanded="false"
                    aria-controls="feedback-outcomes">记录结果</button>
          </div>
          <div class="feedback-outcomes" id="feedback-outcomes" hidden>${outcomeBtns}</div>
        </div>`;
  }

  function renderJobDetail(job, feedback = null) {
    const verdict = VERDICT_LABEL[job.verdict] || job.verdict;
    const meta = [job.company, job.location, job.salary].filter(Boolean).join(" · ");
    const risks = Array.isArray(job.risk_hits) ? job.risk_hits : [];
    const evidence = Array.isArray(job.evidence) ? job.evidence : [];
    const riskNotes = risks.length
      ? `<div class="job-detail__risks">${risks.map(renderRiskNote).join("")}</div>`
      : "";
    const evidenceChain = renderEvidenceChain(evidence, { label: `理由链 · ${evidence.length} 条` });
    return `
        <article class="card job-detail" data-job-url="${esc(job.url)}">
          <header class="job-detail__head">
            ${renderVerdictBadge(job.verdict)}
            <h3 class="card__title">${esc(job.title)}</h3>
          </header>
          <p class="card__meta job-detail__meta">${esc(meta)}</p>
          ${job.url ? `<p class="job-detail__url"><a href="${esc(job.url)}" target="_blank" rel="noopener noreferrer">打开 JD 原文 ↗</a></p>` : ""}

          <div class="job-detail__section">
            <span class="overline">决策理由</span>
            <p class="card__body">${esc(job.reason)}</p>
          </div>

          ${riskNotes}

          ${evidenceChain ? `<div class="job-detail__section">${evidenceChain}</div>` : ""}

          ${renderGapBlock(job)}

          ${renderCompetencyBlock(job)}

          <button class="btn btn--primary job-detail__chat" type="button"
                  data-action="chat-about-job"
                  aria-label="和顾问聊聊这个岗位：${esc(job.title)}">聊聊这个岗位</button>

          ${renderFeedbackRow(job, feedback)}
        </article>`;
  }

  function renderEmptyState({ hasData } = {}) {
    if (hasData) {
      return `<p class="jobs-empty" role="status">${esc(EMPTY_FILTER_HINT)}</p>`;
    }
    return `
        <div class="jobs-empty" role="status">
          <p>还没有决策数据——去对话页聊聊，或先生成一份报告。</p>
          <p><a href="#/chat">去对话页聊聊</a></p>
          <p><a href="#/sources">配置 Boss cookie（平台源）后再生成报告</a></p>
        </div>`;
  }

  /* ---------- DOM 挂载与交互 ---------- */
  function getHost() {
    return document.getElementById("jobs");
  }

  function getList() {
    return document.getElementById("jobs-list");
  }

  function getDetail() {
    return document.getElementById("jobs-detail");
  }

  let partialPromise = null;
  function mountPartial() {
    if (partialPromise) return partialPromise;
    partialPromise = (async () => {
      const host = getHost();
      if (!host || host.querySelector("#jobs-list")) return;
      try {
        const res = await fetch("partials/jobs.html");
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

  function currentJob() {
    return state.jobs.find((j) => j.url === state.selectedUrl) || null;
  }

  async function loadJobs() {
    const list = getList();
    if (!list) return;
    if (state.loaded) {
      renderAll();
      return;
    }
    state.loaded = true;

    if (typeof TalentForgeApi === "undefined" || TalentForgeApi.USE_FIXTURES) {
      state.jobs = LOCAL_FIXTURE_JOBS;
      state.cities = collectCities(state.jobs);
      renderAll();
      return;
    }

    showStatus("正在加载岗位…");
    try {
      const data = await TalentForgeApi.getJobs(state.filters);
      state.jobs = Array.isArray(data) ? data : Array.isArray(data && data.jobs) ? data.jobs : [];
      state.cities = collectCities(state.jobs);
    } catch (err) {
      state.jobs = [];
      state.cities = [];
      showStatus(`岗位加载失败：${err.message}`, "error");
    }
    renderAll();
  }

  function renderAll() {
    renderCityOptions();
    const filtered = filterJobs(state.jobs, state.filters);
    renderList(filtered);
    renderCount(filtered);
    renderDetail();
    applyPendingFocus();
  }

  function renderList(filtered) {
    const list = getList();
    if (!list) return;
    if (!state.jobs.length) {
      list.innerHTML = renderEmptyState({ hasData: false });
      return;
    }
    list.innerHTML = renderJobList(filtered, { selectedUrl: state.selectedUrl });
  }

  function renderDetail() {
    const detail = getDetail();
    if (!detail) return;
    const job = currentJob();
    detail.innerHTML = job
      ? renderJobDetail(job, state.feedback[job.url] || null)
      : `<p class="job-detail__empty">在左侧选择一个岗位，这里会显示决策理由、风险与证据链。</p>`;
  }

  function renderCount(filtered) {
    const el = document.getElementById("jobs-count");
    if (!el) return;
    const stats = countStats(filtered);
    el.textContent = `共 ${stats.total} 个岗位 · 投 ${stats.apply} · 观望 ${stats.hold}`;
  }

  function renderCityOptions() {
    const sel = document.getElementById("jobs-city");
    if (!sel || sel.dataset.filled) return;
    sel.innerHTML =
      `<option value="">全部城市</option>` +
      state.cities.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    sel.dataset.filled = "1";
    sel.value = state.filters.city;
  }

  function selectJob(url) {
    state.selectedUrl = url || "";
    renderAll();
  }

  /** 处理对话页派发的 job:focus（跳转工作台前暂存，进入时定位）。 */
  function onJobFocus(evt) {
    state.pendingFocus = evt.detail || null;
    const host = getHost();
    if (host && !host.hidden) applyPendingFocus();
  }

  function applyPendingFocus() {
    if (!state.pendingFocus) return;
    const focus = state.pendingFocus;
    state.pendingFocus = null;
    const job = state.jobs.find((j) => j.url === focus.url) ||
      state.jobs.find((j) => j.title === focus.title);
    if (job) selectJob(job.url);
  }

  function showStatus(message, tone) {
    const el = document.getElementById("jobs-status");
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("jobs-status--error", tone === "error");
    el.hidden = false;
  }

  function rerenderList() {
    const filtered = filterJobs(state.jobs, state.filters);
    renderList(filtered);
    renderCount(filtered);
  }

  function setVerdictFilter(verdict) {
    state.filters.verdict = verdict;
    updateVerdictButtons();
    rerenderList();
  }

  function updateVerdictButtons() {
    document.querySelectorAll("[data-verdict-filter]").forEach((btn) => {
      const active = (btn.dataset.verdictFilter || "") === (state.filters.verdict || "");
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", String(active));
    });
  }

  /** "聊聊这个岗位"：派发 job:focus 事件（契约同 chat.js openJob）+ 跳对话页。 */
  function chatAboutJob(job) {
    window.dispatchEvent(new CustomEvent("job:focus", { detail: { url: job.url, title: job.title } }));
    if (window.TalentForgeRouter) {
      window.TalentForgeRouter.navigate("/chat");
    }
  }

  function openJd(job) {
    if (job && job.url) {
      window.open(job.url, "_blank", "noopener");
    }
  }

  /** 真模式 POST /api/feedback/events（fetch no-store，参照 sources.js requestJson）。 */
  async function postFeedbackEvent(body) {
    const res = await fetch("/api/feedback/events", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /** 真模式 POST /api/suggest/for-job（fetch no-store，同 postFeedbackEvent 模式）。 */
  async function postSuggestForJob(jobUrl) {
    const res = await fetch("/api/suggest/for-job", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({ job_url: jobUrl }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /** 补信号开合（M6 spec §2.3）：展开 → fixtures 本地示例 / 真模式 for-job 推荐；
      加载态"找项目中…"、失败"后端未启动"；再点收起。 */
  async function toggleSuggest(btn) {
    const section = btn.closest(".job-detail__gaps");
    const box = section && section.querySelector("[data-role='suggest-box']");
    if (!box) return;
    if (!box.hidden) {
      box.hidden = true;
      box.innerHTML = "";
      btn.setAttribute("aria-expanded", "false");
      return;
    }
    box.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    if (typeof TalentForgeApi === "undefined" || TalentForgeApi.USE_FIXTURES) {
      box.innerHTML = renderSuggestBox(LOCAL_SUGGEST_FIXTURES);
      return;
    }
    box.innerHTML = renderSuggestHint(SUGGEST_LOADING_TEXT);
    try {
      const job = currentJob();
      const data = await postSuggestForJob(btn.dataset.jobUrl || (job && job.url) || "");
      box.innerHTML = renderSuggestBox(data);
    } catch (err) {
      console.warn("补信号推荐失败：", err);
      box.innerHTML = renderSuggestHint(SUGGEST_ERROR_TEXT, "error");
    }
  }

  /** 记录反馈（spec §3）：fixtures 本地 mock；真模式 POST 后更新徽章。 */
  async function recordFeedback(job, verdict, outcome = null) {
    if (!job || !job.url) return;
    const applyLocally = () => {
      state.feedback[job.url] = { verdict, outcome, at: new Date() };
      renderDetail();
    };
    if (typeof TalentForgeApi === "undefined" || TalentForgeApi.USE_FIXTURES) {
      applyLocally();
      return;
    }
    try {
      await postFeedbackEvent({
        job_id: job.url,
        job_title: job.title || "",
        decision_verdict: verdict,
        action: outcome ? "outcome" : "decided",
        outcome: outcome || null,
      });
      applyLocally();
    } catch (err) {
      console.warn("feedback 记录失败：", err);
      showStatus("记录失败：后端未启动或稍后重试", "error");
    }
  }

  async function runReport() {
    if (state.reporting) return;
    const btn = document.getElementById("jobs-report");
    const setBusy = (busy) => {
      state.reporting = busy;
      if (btn) {
        btn.disabled = busy;
        btn.textContent = busy ? "报告中…" : "生成报告";
      }
    };

    if (typeof TalentForgeApi === "undefined" || TalentForgeApi.USE_FIXTURES) {
      setBusy(true);
      showStatus("正在抓取并评估岗位…");
      await sleep(1200);
      setBusy(false);
      showStatus("报告已生成（演示）");
      return;
    }

    try {
      setBusy(true);
      showStatus("正在生成报告…");
      await TalentForgeApi.request("/report/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: "后端", city: state.filters.city || undefined, limit: 20 }),
      });
      const maxPoll = 60;
      for (let i = 0; i < maxPoll; i++) {
        await sleep(1000);
        const st = await TalentForgeApi.request("/report/status");
        const stage = st && (st.state || st.status);
        if (stage === "done") {
          showStatus("报告已生成，列表已刷新");
          break;
        }
        if (stage === "failed" || (st && st.error)) {
          showStatus(`报告生成失败：${(st && st.error) || "请稍后重试"}`, "error");
          break;
        }
        if (i === maxPoll - 1) showStatus("报告生成超时，请稍后再试", "error");
      }
      state.loaded = false;
      await loadJobs();
    } catch (err) {
      showStatus(`报告生成失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  function isInteractiveTarget(target) {
    return Boolean(target.closest("button, a, summary, input, textarea, select"));
  }

  function onHostClick(evt) {
    const reportBtn = evt.target.closest("#jobs-report");
    if (reportBtn) {
      evt.preventDefault();
      runReport();
      return;
    }
    const chatBtn = evt.target.closest("[data-action='chat-about-job']");
    if (chatBtn) {
      evt.preventDefault();
      const job = currentJob();
      if (job) chatAboutJob(job);
      return;
    }
    const suggestBtn = evt.target.closest("[data-action='suggest-toggle']");
    if (suggestBtn) {
      evt.preventDefault();
      toggleSuggest(suggestBtn);
      return;
    }
    const decidedBtn = evt.target.closest("[data-action='feedback-decided']");
    if (decidedBtn) {
      evt.preventDefault();
      const job = currentJob();
      if (job) recordFeedback(job, decidedBtn.dataset.verdict);
      return;
    }
    const outcomeToggle = evt.target.closest("[data-action='feedback-outcome-toggle']");
    if (outcomeToggle) {
      evt.preventDefault();
      const row = outcomeToggle.closest(".feedback-row");
      const group = row && row.querySelector(".feedback-outcomes");
      if (group) {
        group.hidden = !group.hidden;
        outcomeToggle.setAttribute("aria-expanded", String(!group.hidden));
      }
      return;
    }
    const outcomeBtn = evt.target.closest("[data-action='feedback-outcome']");
    if (outcomeBtn) {
      evt.preventDefault();
      const job = currentJob();
      if (job) {
        const verdict = (state.feedback[job.url] && state.feedback[job.url].verdict) || "apply";
        recordFeedback(job, verdict, outcomeBtn.dataset.outcome);
      }
      return;
    }
    const editBtn = evt.target.closest("[data-action='feedback-edit']");
    if (editBtn) {
      evt.preventDefault();
      const job = currentJob();
      if (job) {
        delete state.feedback[job.url];
        renderDetail();
      }
      return;
    }
    const filterBtn = evt.target.closest("[data-verdict-filter]");
    if (filterBtn) {
      evt.preventDefault();
      setVerdictFilter(filterBtn.dataset.verdictFilter);
      return;
    }
    const row = evt.target.closest("[data-job-url]");
    if (row && !isInteractiveTarget(evt.target)) {
      evt.preventDefault();
      selectJob(row.dataset.jobUrl);
    }
  }

  function onHostDblclick(evt) {
    const row = evt.target.closest("[data-job-url]");
    if (!row || isInteractiveTarget(evt.target)) return;
    const job = state.jobs.find((j) => j.url === row.dataset.jobUrl);
    if (job) openJd(job);
  }

  function onHostKeydown(evt) {
    if (evt.key !== "Enter") return;
    const row = evt.target.closest("[data-job-url]");
    if (row && !isInteractiveTarget(evt.target)) {
      evt.preventDefault();
      selectJob(row.dataset.jobUrl);
    }
  }

  function wireEvents() {
    const host = getHost();
    if (host) {
      host.addEventListener("click", onHostClick);
      host.addEventListener("dblclick", onHostDblclick);
      host.addEventListener("keydown", onHostKeydown);
    }
    const q = document.getElementById("jobs-q");
    if (q) q.addEventListener("input", () => { state.filters.q = q.value; rerenderList(); });
    const city = document.getElementById("jobs-city");
    if (city) city.addEventListener("change", () => { state.filters.city = city.value; rerenderList(); });
  }

  function onEnterJobs() {
    mountPartial().then(loadJobs);
  }

  function init() {
    if (window.TalentForgeRouter && typeof window.TalentForgeRouter.onView === "function") {
      window.TalentForgeRouter.onView("jobs", onEnterJobs);
    } else {
      window.addEventListener("route:change", (evt) => {
        if (evt.detail && evt.detail.view === "jobs") onEnterJobs();
      });
    }
    if (window.TalentForgeRouter && window.TalentForgeRouter.currentPath() === "/jobs") {
      onEnterJobs();
    }
    window.addEventListener("job:focus", onJobFocus);
  }

  return {
    DEFAULT_RISK_WHY,
    EMPTY_FILTER_HINT,
    FEEDBACK_VERDICT_LABEL,
    LOCAL_FIXTURE_JOBS,
    LOCAL_SUGGEST_FIXTURES,
    OUTCOME_LABEL,
    SEVERITY_LABEL,
    SUGGEST_ERROR_TEXT,
    SUGGEST_LOADING_TEXT,
    SUGGEST_NO_GAPS_HINT,
    clip,
    collectCities,
    countStats,
    esc,
    filterJobs,
    fmtAt,
    fmtDay,
    fmtIsoDay,
    normalizeGaps,
    renderCompetencyBlock,
    renderCompetencyRow,
    renderEmptyState,
    renderEvidenceChain,
    renderFeedbackRow,
    renderGapBlock,
    renderGapItem,
    renderJobDetail,
    renderJobList,
    renderJobRow,
    renderRiskNote,
    renderRiskTag,
    renderSuggestBox,
    renderSuggestCard,
    renderSuggestHint,
    renderVerdictBadge,
    init,
  };
})();

if (typeof window !== "undefined") {
  window.TalentForgeJobs = TalentForgeJobs;
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => TalentForgeJobs.init());
  } else {
    TalentForgeJobs.init();
  }
}
