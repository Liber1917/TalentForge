// Firefox 兼容层：Gecko manifest 变体派生 + alarm 周期钳制。
// 纯函数、零依赖 —— 构建脚本（scripts/build-extension.mjs 经 node 原生
// type-stripping 直接 import）与 vitest 共用这一份实现。
export const FIREFOX_GECKO_ID = "talentforge@local";
// 142.0 起桌面与 Android 均识别 data_collection_permissions（addons-linter
// 要求新扩展声明该键；桌面 140 / Android 142 引入支持，取交集）。
export const FIREFOX_STRICT_MIN_VERSION = "142.0";

/** Firefox 把 periodInMinutes < 1 的 alarm 周期钳到 1 分钟（MDN alarms.create）。 */
export const FIREFOX_MIN_ALARM_PERIOD_MINUTES = 1;

interface BaseManifest {
  manifest_version: number;
  name: string;
  version: string;
  permissions: string[];
  host_permissions: string[];
  content_scripts: Array<{
    matches: string[];
    js: string[];
    run_at?: string;
  }>;
  background: { service_worker: string; type?: string };
}

export interface FirefoxManifest extends Omit<BaseManifest, "background"> {
  background: { scripts: string[] };
  browser_specific_settings: {
    gecko: {
      id: string;
      strict_min_version: string;
      /** AMO 对新扩展的必填声明：本扩展不采集任何技术数据。 */
      data_collection_permissions: { required: string[] };
    };
  };
}

/**
 * Derive a Gecko-loadable manifest from the Chrome base manifest:
 * `background.service_worker` → `background.scripts`（Firefox MV3 不支持
 * service worker，事件页用经典脚本加载），并补上 browser_specific_settings。
 * script 路径去掉 "dist/" 前缀 —— 基准 manifest 的路径相对项目根解析
 * （Chrome 从仓库根加载），而 dist-firefox/ 是自包含的可加载目录。
 * 其余字段（permissions/host_permissions/matches 等）原样沿用。
 * 输入必须是已解析的合法基准 manifest，否则抛错（构建期 fail-fast）。
 */
export function buildFirefoxManifest(base: unknown): FirefoxManifest {
  if (typeof base !== "object" || base === null) {
    throw new Error("buildFirefoxManifest: base manifest must be a parsed object");
  }
  const manifest = base as Partial<BaseManifest>;
  const serviceWorker = manifest.background?.service_worker;
  if (typeof serviceWorker !== "string" || serviceWorker.trim() === "") {
    throw new Error("buildFirefoxManifest: base manifest lacks background.service_worker");
  }
  const stripDistPrefix = (path: string): string =>
    path.startsWith("dist/") ? path.slice("dist/".length) : path;
  const { background: _chromeBackground, content_scripts, ...rest } = manifest;
  void _chromeBackground;
  return {
    ...(rest as Omit<BaseManifest, "background" | "content_scripts">),
    background: { scripts: [stripDistPrefix(serviceWorker)] },
    content_scripts: (content_scripts ?? []).map((cs) => ({
      ...cs,
      js: cs.js.map(stripDistPrefix),
    })),
    browser_specific_settings: {
      gecko: {
        id: FIREFOX_GECKO_ID,
        strict_min_version: FIREFOX_STRICT_MIN_VERSION,
        // addons-linter 要求新扩展显式声明数据采集口径：none = 不采集。
        data_collection_permissions: { required: ["none"] },
      },
    },
  };
}

/**
 * Clamp an alarm period to the target's minimum: Firefox enforces 1 minute,
 * so we clamp explicitly instead of relying on the browser's implicit clamp.
 */
export function clampAlarmPeriodForFirefox(
  periodMinutes: number,
  isFirefox: boolean,
): number {
  if (!Number.isFinite(periodMinutes) || periodMinutes <= 0) {
    return FIREFOX_MIN_ALARM_PERIOD_MINUTES;
  }
  return isFirefox
    ? Math.max(periodMinutes, FIREFOX_MIN_ALARM_PERIOD_MINUTES)
    : periodMinutes;
}
