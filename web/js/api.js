/* =========================================================
   TalentForge API 层：fetch 封装 + 数据读取
   - base：真后端为 /api；开发期 USE_FIXTURES=true 切 /api/fixtures 假数据前缀
   - 暴露 getChat / getJobs / getProfile，均返回 Promise
   - 失败时 reject，附带可读中文错误（HTTP 状态 / 网络 / 超时）
   ========================================================= */

"use strict";

const TalentForgeApi = (() => {
  /* 数据源开关（运行时切换）：
     - 默认 fixtures 假数据（离线开箱即用，三视图本地镜像数据）
     - 真后端联调：URL 加 ?real=1 或 localStorage 设 tf_real=1（base 切 /api）
     优先级：URL 参数 > localStorage > 默认。 */
  const _wantReal =
    new URLSearchParams(window.location.search).get("real") === "1" ||
    window.localStorage.getItem("tf_real") === "1";
  /* M12（D31 演示沙箱）：新手引导可运行时强制 fixture 模式（内存 flag，
     不落 storage）；null = 无覆盖，回落 URL/localStorage 的默认判定。 */
  let _fixtureOverride = null;

  function _wantRealNow() {
    if (_fixtureOverride !== null) return !_fixtureOverride;
    return _wantReal;
  }

  function _baseNow() {
    return _wantRealNow() ? "/api" : "/api/fixtures";
  }

  /** 沙箱开关：true=强制假数据，false=强制真后端，null=还原默认。 */
  function setFixtureOverride(value) {
    _fixtureOverride = value === null ? null : Boolean(value);
  }

  const TIMEOUT_MS = 10000;

  /**
   * 统一 fetch 封装。
   * @param {string} path 相对 base 的路径（如 "/chat/turns"）
   * @param {object} [options] fetch 选项（method/body/headers…）
   * @returns {Promise<object>} 解析后的 JSON
   */
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
      const res = await fetch(`${_baseNow()}${path}`, {
        headers: { Accept: "application/json" },
        ...options,
        signal: controller.signal,
      });

      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`请求失败（${res.status}）：${detail || "服务器返回了错误状态"}`);
      }

      return await res.json();
    } catch (err) {
      if (err && err.name === "AbortError") {
        throw new Error("请求超时：请确认后端服务已启动（127.0.0.1:8420）");
      }
      if (err && err.name === "TypeError") {
        throw new Error("网络错误：无法连接后端服务，请确认已启动");
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  /** 对话流历史（spec §1：GET /api/chat/turns → [{role,text,cards,at}]）。 */
  function getChat() {
    return request("/chat/turns");
  }

  /** 发送对话轮次（spec §1：POST /api/chat/turns，反思回答带 reply_to）。 */
  function postTurn(payload = {}) {
    return request("/chat/turns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  /** 主张确认（spec §1：POST /api/claims/{id}/confirm → state=active）。 */
  function confirmClaim(id) {
    return request(`/claims/${encodeURIComponent(id)}/confirm`, { method: "POST" });
  }

  /** 主张驳回（spec §1：POST /api/claims/{id}/reject → state=archived）。 */
  function rejectClaim(id) {
    return request(`/claims/${encodeURIComponent(id)}/reject`, { method: "POST" });
  }

  /** 岗位列表（spec §2：GET /api/jobs?city=&verdict=&q=）。
   *  @param {object} [params] 筛选参数（city/verdict/q） */
  function getJobs(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return request(`/jobs${qs ? `?${qs}` : ""}`);
  }

  /** 画像全量（spec §3：GET /api/profile）。 */
  function getProfile() {
    return request("/profile");
  }

  return {
    get USE_FIXTURES() {
      return !_wantRealNow();
    },
    get BASE() {
      return _baseNow();
    },
    setFixtureOverride,
    getChat,
    getJobs,
    getProfile,
    postTurn,
    confirmClaim,
    rejectClaim,
    request,
  };
})();

if (typeof window !== "undefined") {
  window.TalentForgeApi = TalentForgeApi;
}
