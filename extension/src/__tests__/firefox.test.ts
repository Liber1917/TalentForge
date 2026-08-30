// Firefox 兼容层单测：manifest 变体派生 + alarm 周期钳制（构建脚本与
// 此处共用 src/shared/firefox.ts 的同一份实现）。
import { describe, expect, it } from "vitest";
import {
  FIREFOX_GECKO_ID,
  FIREFOX_MIN_ALARM_PERIOD_MINUTES,
  FIREFOX_STRICT_MIN_VERSION,
  buildFirefoxManifest,
  clampAlarmPeriodForFirefox,
} from "../shared/firefox";

function makeBaseManifest(): Record<string, unknown> {
  return {
    manifest_version: 3,
    name: "TalentForge",
    version: "0.1.0",
    permissions: ["storage", "alarms"],
    background: {
      service_worker: "dist/background/service-worker.js",
      type: "module",
    },
    host_permissions: [
      "http://127.0.0.1/*",
      "*://*.bilibili.com/*",
      "*://*.zhihu.com/*",
      "*://*.zhipin.com/*",
    ],
    content_scripts: [
      {
        matches: ["*://*.bilibili.com/*"],
        js: ["dist/content/bilibili.js"],
        run_at: "document_idle",
      },
    ],
  };
}

describe("buildFirefoxManifest", () => {
  it("replaces service_worker with background.scripts and never keeps both", () => {
    const manifest = buildFirefoxManifest(makeBaseManifest());
    expect(manifest.background).toEqual({ scripts: ["background/service-worker.js"] });
    expect("service_worker" in manifest.background).toBe(false);
    expect("type" in manifest.background).toBe(false);
  });

  it("rewrites script paths relative to dist-firefox/ (strips the dist/ prefix)", () => {
    const manifest = buildFirefoxManifest(makeBaseManifest());
    expect(manifest.content_scripts).toEqual([
      {
        matches: ["*://*.bilibili.com/*"],
        js: ["content/bilibili.js"],
        run_at: "document_idle",
      },
    ]);
  });

  it("adds gecko id and a strict_min_version >= 121", () => {
    const gecko = buildFirefoxManifest(makeBaseManifest())
      .browser_specific_settings.gecko;
    expect(gecko.id).toBe(FIREFOX_GECKO_ID);
    expect(Number.parseInt(FIREFOX_STRICT_MIN_VERSION, 10)).toBeGreaterThanOrEqual(121);
    expect(gecko.strict_min_version).toBe(FIREFOX_STRICT_MIN_VERSION);
    expect(gecko.data_collection_permissions).toEqual({ required: ["none"] });
  });

  it("uses a min version that recognizes data_collection_permissions (>= 140 desktop / 142 android)", () => {
    expect(Number.parseInt(FIREFOX_STRICT_MIN_VERSION, 10)).toBeGreaterThanOrEqual(140);
  });

  it("preserves permissions, host_permissions and top-level fields verbatim", () => {
    const base = makeBaseManifest();
    const manifest = buildFirefoxManifest(base);
    expect(manifest.permissions).toEqual(base.permissions);
    expect(manifest.host_permissions).toEqual(base.host_permissions);
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.name).toBe("TalentForge");
    expect(manifest.version).toBe("0.1.0");
  });

  it("does not mutate the input manifest", () => {
    const base = makeBaseManifest();
    const snapshot = JSON.parse(JSON.stringify(base)) as Record<string, unknown>;
    buildFirefoxManifest(base);
    expect(base).toEqual(snapshot);
  });

  it("throws on invalid base manifests", () => {
    expect(() => buildFirefoxManifest(null)).toThrow();
    expect(() => buildFirefoxManifest("nope")).toThrow();
    expect(() => buildFirefoxManifest({ manifest_version: 3 })).toThrow();
    expect(() =>
      buildFirefoxManifest({ background: { service_worker: "" } }),
    ).toThrow();
  });
});

describe("clampAlarmPeriodForFirefox", () => {
  it("keeps sub-minute periods on chrome runtimes", () => {
    expect(clampAlarmPeriodForFirefox(0.5, false)).toBe(0.5);
  });

  it("clamps sub-minute periods up to 1 minute on firefox runtimes", () => {
    expect(clampAlarmPeriodForFirefox(0.5, true)).toBe(FIREFOX_MIN_ALARM_PERIOD_MINUTES);
  });

  it("leaves >=1 minute periods untouched on firefox runtimes", () => {
    expect(clampAlarmPeriodForFirefox(5, true)).toBe(5);
    expect(clampAlarmPeriodForFirefox(FIREFOX_MIN_ALARM_PERIOD_MINUTES, true)).toBe(1);
  });

  it("falls back to the firefox minimum for invalid periods", () => {
    expect(clampAlarmPeriodForFirefox(Number.NaN, true)).toBe(1);
    expect(clampAlarmPeriodForFirefox(0, false)).toBe(1);
    expect(clampAlarmPeriodForFirefox(-3, false)).toBe(1);
  });
});
