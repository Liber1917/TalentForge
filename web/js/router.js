/* =========================================================
   TalentForge Hash 路由器（无框架 vanilla）
   路由：#/chat（对话首页）· #/jobs（决策工作台）· #/profile（画像面板）
   默认：#/chat。未知 hash 回退默认。
   - 切换 data-view 视图显隐
   - 导航 tab 高亮（aria-current="page"）
   - 同步底部状态条"当前视图"
   - 广播 route:change 事件（视图层订阅）
   ========================================================= */

"use strict";

const AppRouter = (() => {
  const ROUTES = {
    "/chat": "chat",
    "/jobs": "jobs",
    "/profile": "profile",
  };
  const DEFAULT_ROUTE = "/chat";
  const LABELS = { "/chat": "对话", "/jobs": "工作台", "/profile": "画像" };

  /** 从 location.hash 解析出合法路由路径。 */
  function currentPath() {
    const raw = (window.location.hash || "").replace(/^#/, "");
    return ROUTES[raw] ? raw : DEFAULT_ROUTE;
  }

  /** 切换视图 + 导航高亮 + 更新状态条 + 广播事件。 */
  function setActiveView(path) {
    const view = ROUTES[path];

    document.querySelectorAll("[data-view]").forEach((el) => {
      el.hidden = el.dataset.view !== view;
    });

    document.querySelectorAll(".nav__tab").forEach((link) => {
      const active = link.getAttribute("href") === `#${path}`;
      link.classList.toggle("is-active", active);
      if (active) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });

    const statusEl = document.getElementById("status-view");
    if (statusEl) {
      statusEl.textContent = `当前视图：${LABELS[path] || view}`;
    }

    window.dispatchEvent(new CustomEvent("route:change", { detail: { view, path } }));
  }

  /** 程序化跳转（供"聊聊这个岗位"等跨页操作使用）。 */
  function navigate(path) {
    if (!ROUTES[path]) path = DEFAULT_ROUTE;
    if (currentPath() === path) {
      setActiveView(path);
    } else {
      window.location.hash = path;
    }
  }

  function handleRoute() {
    setActiveView(currentPath());
  }

  function init() {
    if (!window.location.hash) {
      window.location.replace(`#${DEFAULT_ROUTE}`);
    }
    handleRoute();
    window.addEventListener("hashchange", handleRoute);
  }

  return { ROUTES, DEFAULT_ROUTE, init, currentPath, navigate, setActiveView };
})();

if (typeof window !== "undefined") {
  window.TalentForgeRouter = AppRouter;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => AppRouter.init());
  } else {
    AppRouter.init();
  }
}
