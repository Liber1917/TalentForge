// 发布目录 manifest 派生：仓库根相对路径 → 自包含加载目录。
// 基准 manifest 的 script 路径相对仓库根（开发态 Chrome Load unpacked 指向
// extension/），而 dist/ 与 dist-firefox/ 是自包含发布目录——打进 zip 后必须
// 去掉 "dist/" 前缀，否则解压目录里找不到引用文件（Chrome 加载失败；
// Firefox 变体因同款去前缀而幸免——用户反馈实证）。
export function stripDistPath(path: string): string {
  return path.startsWith("dist/") ? path.slice("dist/".length) : path;
}

interface BaseManifest {
  background?: { service_worker?: string; type?: string };
  content_scripts?: Array<{ js: string[] }>;
}

export interface ChromeDistManifest {
  background: { service_worker: string; type?: string };
  content_scripts: Array<{ js: string[] } & Record<string, unknown>>;
  [key: string]: unknown;
}

/**
 * Derive a self-contained dist/ manifest from the repo-root base manifest:
 * identical shape, script paths stripped of the "dist/" prefix, so the
 * unzipped release folder loads directly in Chrome (zip root = dist root).
 * The repo-root manifest itself stays untouched for the dev "Load unpacked"
 * flow. Input must be a parsed valid base manifest, else throws (build-time
 * fail-fast).
 */
export function buildChromeDistManifest(base: unknown): ChromeDistManifest {
  if (typeof base !== "object" || base === null) {
    throw new Error("buildChromeDistManifest: base manifest must be a parsed object");
  }
  const manifest = base as Partial<BaseManifest>;
  const serviceWorker = manifest.background?.service_worker;
  if (typeof serviceWorker !== "string" || serviceWorker.trim() === "") {
    throw new Error("buildChromeDistManifest: base manifest lacks background.service_worker");
  }
  const { background: _chromeBackground, content_scripts, ...rest } = manifest;
  void _chromeBackground;
  return {
    ...(rest as Record<string, unknown>),
    background: {
      type: manifest.background?.type,
      service_worker: stripDistPath(serviceWorker),
    },
    content_scripts: (content_scripts ?? []).map((cs) => ({
      ...cs,
      js: cs.js.map(stripDistPath),
    })),
  };
}
