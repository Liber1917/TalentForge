// Chrome 发布目录 manifest 派生：仓库根相对路径 → dist/ 自包含。
// 历史 bug：dist/manifest.json 逐字节复制基准（路径带 "dist/" 前缀），
// CI zip 以 dist/ 为根打包后，Chrome 解压加载找不到 dist/... 文件——
// Firefox 变体因专门去前缀而幸免（用户反馈：Chrome 加载不了、Firefox 能加载）。
import { describe, expect, it } from "vitest";
import { buildChromeDistManifest, stripDistPath } from "../shared/dist-manifest";

const BASE = {
  manifest_version: 3,
  name: "TalentForge",
  version: "0.1.0",
  permissions: ["storage", "alarms"],
  host_permissions: ["*://*.bilibili.com/*", "http://127.0.0.1/*"],
  background: { service_worker: "dist/background/service-worker.js", type: "module" },
  content_scripts: [
    { matches: ["*://*.bilibili.com/*"], js: ["dist/content/bilibili.js"] },
    { matches: ["*://*.zhipin.com/*"], js: ["dist/content/boss.js"] },
  ],
};

describe("stripDistPath", () => {
  it("removes the dist/ prefix and leaves other paths untouched", () => {
    expect(stripDistPath("dist/background/service-worker.js")).toBe(
      "background/service-worker.js",
    );
    expect(stripDistPath("background/service-worker.js")).toBe("background/service-worker.js");
  });
});

describe("buildChromeDistManifest", () => {
  it("strips dist/ prefixes from service_worker and content script js paths", () => {
    const m = buildChromeDistManifest(BASE);
    expect(m.background.service_worker).toBe("background/service-worker.js");
    expect(m.background.type).toBe("module");
    expect(m.content_scripts.map((cs) => cs.js)).toEqual([
      ["content/bilibili.js"],
      ["content/boss.js"],
    ]);
  });

  it("keeps every other field verbatim and adds no gecko settings", () => {
    const m = buildChromeDistManifest(BASE);
    expect(m.name).toBe("TalentForge");
    expect(m.version).toBe("0.1.0");
    expect(m.permissions).toEqual(["storage", "alarms"]);
    expect(m.host_permissions).toEqual(BASE.host_permissions);
    expect(
      (m as Record<string, unknown>).browser_specific_settings,
    ).toBeUndefined();
  });

  it("does not mutate the input manifest", () => {
    const input = JSON.parse(JSON.stringify(BASE));
    buildChromeDistManifest(input);
    expect(input.background.service_worker).toBe("dist/background/service-worker.js");
  });

  it("throws on non-object input or missing background.service_worker", () => {
    expect(() => buildChromeDistManifest(null)).toThrow();
    expect(() => buildChromeDistManifest({ manifest_version: 3 })).toThrow();
    expect(() => buildChromeDistManifest({ background: {} })).toThrow();
  });
});
