"""Boss 反自动化对抗层（来源：get_jobs Discussion #250 逆向结论 + 本地实证）。

Boss 集成 disable-devtool 库 + CDP/WebDriver 检测，程序驱动的页面会被
``window.location.href='about:blank'`` 关闭。已实证有效的三层缓解：
1. console 钩子：console.table 等置空（击穿其"console.table 计时"检测）+
   Function.prototype.toString 伪装 [native code]（Boss 有"函数是否被覆盖"埋点上报，
   被替换的钩子与 toString 自身都要在伪装表内，否则伪装本身可被检测）；
2. performance.now 降精度（微秒级时间差检测）；
3. 启动参数 --disable-blink-features=AutomationControlled（引擎级抹 webdriver 特征）。

实测（2026-08，chromium headless）：注入后 zhipin 页面存活并可正常跳转登录页。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

LAUNCH_ARGS: tuple[str, ...] = (
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
)

STEALTH_INIT_SCRIPT = """
(() => {
  const masked = new Map();
  for (const name of ["log", "table", "warn", "info", "debug", "error"]) {
    const replacement = function () {};
    masked.set(replacement, name);
    console[name] = replacement;
  }
  const origToString = Function.prototype.toString;
  const patchedToString = function toString(...args) {
    const name = masked.get(this);
    if (name !== undefined) return `function ${name}() { [native code] }`;
    return origToString.apply(this, args);
  };
  masked.set(patchedToString, "toString");
  Function.prototype.toString = patchedToString;
  const origNow = performance.now.bind(performance);
  const patchedNow = function now() {
    return Math.round(origNow() * 100) / 100;
  };
  masked.set(patchedNow, "now");
  performance.now = patchedNow;
})();
"""


def apply_stealth(context: BrowserContext) -> None:
    """给 BrowserContext 注入反检测脚本（作用于后续所有页面与 iframe）。"""
    context.add_init_script(STEALTH_INIT_SCRIPT)
