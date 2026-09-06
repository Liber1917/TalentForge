/* =========================================================
   TalentForge 新手引导（M12，D31 演示沙箱）
   - 六步引导流：欢迎 → 决策卡 → 工作台 → 画像 → 采集 → 切真
   - 沙箱红线：进入强制 fixture（api.setFixtureOverride(true)），
     退出还原 tf_real 原值；引导状态只写 tf_tour_* 命名空间
   - 假数据为视图内嵌 LOCAL_FIXTURE_*，交互全客户端 mock，
     后端无 /api/fixtures 路由（写请求物理上不可能触达真库）
   - 入口：顶栏常驻按钮 + 首启建议卡（.tf-tour-start-btn，
     由本模块统一事件委托，视图无需自行绑定）
   ========================================================= */

"use strict";

const STEPS = [
  {
    id: "welcome",
    view: "/chat",
    target: "#chat-input",
    title: "欢迎来到 TalentForge",
    body:
      "这是你的求职决策伙伴：陪你聊方向、看岗位、做判断——不是替你海投简历。" +
      "接下来用演示数据带你走一遍核心概念（约 2 分钟，随时可按 Esc 退出）。",
  },
  {
    id: "decision-card",
    view: "/chat",
    target: ".chat-bubble--cards",
    title: "决策卡：每个判断都可解释",
    body:
      "对话里出现的卡片就是决策结论——投（apply）/ 观望（hold）/ 跳过（skip）三态，" +
      "附理由链与风险标签（如 996、竞业限制）。你可以说不，系统只提供知情依据。",
  },
  {
    id: "workbench",
    view: "/jobs",
    target: null,
    title: "工作台：岗位三态全景",
    body:
      "所有评估过的岗位按 投/观望/跳过 分列，可筛选。点开卡片看详情：" +
      "差距（gap）告诉你补什么短板，风险提示告诉你需要核实什么。",
  },
  {
    id: "profile",
    view: "/profile",
    target: null,
    title: "画像：系统这样认识你",
    body:
      "叙事双轨（你是谁/你要什么）+ 八格结构位置（现金缓冲、城市约束、硬边界…）。" +
      "它从你的对话与行为中慢慢生长，待定主张由你确认——你随时可以校对。",
  },
  {
    id: "sources",
    view: "/sources",
    target: null,
    title: "数据从哪来：浏览器扩展",
    body:
      "岗位与行为数据由浏览器扩展在你正常浏览 Boss/B站/知乎 时采集入库，" +
      "全部留在本机。配置一次，之后不需要额外操作。",
  },
  {
    id: "go-real",
    view: null,
    target: ".tf-tour-banner",
    title: "现在切到真实模式",
    body:
      "你刚才看到的全是演示数据——没有写入你的任何真实信息。装好扩展、配好模型后，" +
      "点本横幅或用 ?real=1 切换到真实模式，开始你自己的决策之旅。",
  },
];

const KEY_DONE = "tf_tour_done";
const KEY_ACTIVE = "tf_tour_active";
const KEY_REAL = "tf_real";

/**
 * 引导核心状态机（纯逻辑，node --test 直接覆盖）。
 * deps: { storage, setFixtureOverride, navigate(hash), onStep(step|null) }
 */
function createTourCore(deps) {
  const state = { active: false, index: 0, prevReal: null };

  function goTo(index) {
    if (!state.active) return;
    const n = Math.max(0, Math.min(STEPS.length - 1, index));
    state.index = n;
    const step = STEPS[n];
    if (step.view) deps.navigate(step.view);
    deps.onStep(step);
  }

  function start() {
    if (state.active) return false;
    state.active = true;
    state.index = 0;
    state.prevReal = deps.storage.getItem(KEY_REAL);
    deps.setFixtureOverride(true);
    try {
      deps.storage.setItem(KEY_ACTIVE, "1");
    } catch (err) {
      // storage 只影响审计可见性，失败不阻断引导
    }
    goTo(0);
    return true;
  }

  function next() {
    if (!state.active) return;
    if (state.index >= STEPS.length - 1) {
      stop();
      return;
    }
    goTo(state.index + 1);
  }

  function prev() {
    if (!state.active) return;
    goTo(state.index - 1);
  }

  function stop() {
    if (!state.active) return false;
    /* D31 红线②：退出还原 tf_real 原值（进入前保存的） */
    try {
      if (state.prevReal === null) {
        deps.storage.removeItem(KEY_REAL);
      } else {
        deps.storage.setItem(KEY_REAL, state.prevReal);
      }
      deps.storage.removeItem(KEY_ACTIVE);
      deps.storage.setItem(KEY_DONE, "1");
    } catch (err) {
      // storage 失败不阻断退出；override 仍会在下方还原
    }
    deps.setFixtureOverride(null);
    deps.onStep(null);
    state.active = false;
    return true;
  }

  return { start, stop, next, prev, goTo, state: () => ({ ...state }), STEPS };
}

/* ---------------- DOM 装配（浏览器环境） ---------------- */

function _ensureEl(doc, id, cls, html) {
  let el = doc.getElementById(id);
  if (!el) {
    el = doc.createElement("div");
    el.id = id;
    el.className = cls;
    doc.body.appendChild(el);
  }
  if (html !== undefined) el.innerHTML = html;
  return el;
}

function _trySpotlight(doc, step, attempt) {
  if (!step || !step.target || attempt > 6) return;
  const el = doc.querySelector(step.target);
  if (el) {
    el.classList.add("tf-tour-spotlight");
    return;
  }
  setTimeout(() => _trySpotlight(doc, step, attempt + 1), 350);
}

function _clearSpotlight(doc) {
  doc.querySelectorAll(".tf-tour-spotlight").forEach((el) => {
    el.classList.remove("tf-tour-spotlight");
  });
}

function initTour(win, doc) {
  const core = createTourCore({
    storage: win.localStorage,
    setFixtureOverride: (value) => {
      const api = win.TalentForgeApi;
      if (api && typeof api.setFixtureOverride === "function") {
        api.setFixtureOverride(value);
      }
    },
    navigate: (hash) => {
      if (win.location.hash !== hash) win.location.hash = hash;
    },
    onStep: (step) => {
      _clearSpotlight(doc);
      if (!step) {
        ["tf-tour-banner", "tf-tour-card", "tf-tour-overlay"].forEach((id) => {
          const el = doc.getElementById(id);
          if (el) el.remove();
        });
        return;
      }
      _ensureEl(
        doc,
        "tf-tour-banner",
        "tf-tour-banner",
        '<span class="tf-tour-banner__dot" aria-hidden="true"></span>演示数据——不会写入你的真实数据' +
          '<button type="button" class="tf-tour-banner__exit">退出引导</button>',
      );
      doc.getElementById("tf-tour-banner")
        .querySelector(".tf-tour-banner__exit")
        .addEventListener("click", () => core.stop());
      _ensureEl(doc, "tf-tour-overlay", "tf-tour-overlay", "");
      const n = core.state().index + 1;
      _ensureEl(
        doc,
        "tf-tour-card",
        "tf-tour-card",
        `<div class="tf-tour-card__step">${n} / ${STEPS.length}</div>` +
          `<h3 class="tf-tour-card__title">${step.title}</h3>` +
          `<p class="tf-tour-card__body">${step.body}</p>` +
          `<div class="tf-tour-card__actions">` +
          `<button type="button" class="tf-tour-card__btn" data-act="prev" ${n <= 1 ? "disabled" : ""}>上一步</button>` +
          `<button type="button" class="tf-tour-card__btn tf-tour-card__btn--primary" data-act="next">` +
          `${n >= STEPS.length ? "完成" : "下一步"}</button>` +
          `<button type="button" class="tf-tour-card__btn" data-act="skip">跳过</button>` +
          `</div>`,
      );
      doc.getElementById("tf-tour-card")
        .querySelectorAll("[data-act]")
        .forEach((btn) => {
          btn.addEventListener("click", () => {
            const act = btn.getAttribute("data-act");
            if (act === "prev") core.prev();
            else if (act === "next") core.next();
            else core.stop();
          });
        });
      _trySpotlight(doc, step, 0);
    },
  });

  doc.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && core.state().active) core.stop();
  });
  /* 统一入口委托：顶栏常驻按钮 + 首启建议卡按钮，视图无需各自绑定 */
  doc.addEventListener("click", (e) => {
    const hit = e.target.closest("#tf-tour-btn, .tf-tour-start-btn");
    if (hit) core.start();
  });

  return {
    start: core.start,
    stop: core.stop,
    isActive: () => core.state().active,
    steps: STEPS,
    createTourCore,
  };
}

const TalentForgeTour =
  typeof window !== "undefined" && typeof document !== "undefined"
    ? initTour(window, document)
    : { createTourCore, steps: STEPS };

if (typeof window !== "undefined") {
  window.TalentForgeTour = TalentForgeTour;
}
