// Extension build: content scripts MUST be self-contained classic scripts —
// Chrome content_scripts don't support ES module imports (SyntaxError on
// injection). So each content entry gets its own single-input IIFE build
// (shared deps like kernel/backend-endpoint get inlined per file), while the
// service worker stays an ES module (manifest declares "type": "module").
//
// Targets (--target=chrome|firefox or TARGET env var, default chrome):
//   chrome  → dist/          ES-module service worker + self-contained
//                            manifest (dist/ prefixes stripped — the unzipped
//                            folder loads directly; dev "Load unpacked" on
//                            extension/ keeps using the repo-root manifest).
//   firefox → dist-firefox/  IIFE background (Firefox MV3 has no service
//                            worker; background.scripts loads a classic
//                            script) + derived Gecko manifest variant.
import { build } from "vite";
import { fileURLToPath } from "node:url";
import { readFileSync, statSync, writeFileSync } from "node:fs";
import { buildChromeDistManifest } from "../src/shared/dist-manifest.ts";
import { buildFirefoxManifest } from "../src/shared/firefox.ts";

const entry = (p) => fileURLToPath(new URL(`../${p}`, import.meta.url));

const targetArg = process.argv
  .find((arg) => arg.startsWith("--target="))
  ?.slice("--target=".length);
const target =
  targetArg ?? process.env.TARGET ?? process.env.TALENTFORGE_TARGET ?? "chrome";
if (target !== "chrome" && target !== "firefox") {
  throw new Error(`Unknown build target: ${target} (expected chrome|firefox)`);
}
const isFirefox = target === "firefox";
const outDir = isFirefox ? "dist-firefox" : "dist";

// 1. Background first (empties outDir). Chrome keeps the ES-module service
// worker; Firefox needs a classic script for background.scripts (event page).
await build({
  build: {
    outDir,
    emptyOutDir: true,
    target: "es2022",
    rollupOptions: {
      input: { "background/service-worker": entry("./src/background/service-worker.ts") },
      output: {
        format: isFirefox ? "iife" : "es",
        entryFileNames: "[name].js",
      },
    },
  },
});

// 2. Content scripts: one IIFE build per entry — no imports, no shared chunks.
// Identical for both targets (content_scripts are classic scripts everywhere).
for (const name of ["content/bilibili", "content/zhihu", "content/boss"]) {
  await build({
    build: {
      outDir,
      emptyOutDir: false,
      target: "es2022",
      rollupOptions: {
        input: { [name]: entry(`./src/${name}.ts`) },
        output: { format: "iife", entryFileNames: "[name].js" },
      },
    },
  });
}

// 3. Stage a SELF-CONTAINED manifest into the output folder root: script
// paths stripped of the "dist/" prefix (zip root = folder root; the unzipped
// folder loads directly). Firefox additionally derives the Gecko variant.
// 历史 bug：chrome 曾逐字节复制基准 manifest（路径带 dist/ 前缀），CI zip
// 解压后 Chrome 找不到 dist/... 文件——Firefox 因同款去前缀而幸免。
const base = JSON.parse(
  readFileSync(new URL("../manifest.json", import.meta.url), "utf8"),
);
writeFileSync(
  new URL(`../${outDir}/manifest.json`, import.meta.url),
  `${JSON.stringify(
    isFirefox ? buildFirefoxManifest(base) : buildChromeDistManifest(base),
    null,
    2,
  )}\n`,
);

// 4. Smoke check the staged artifact: manifest must parse, no script path may
// carry the "dist/" prefix (self-containment — the unzipped folder must load
// in a browser), every referenced script must exist non-empty inside outDir,
// and the background shape must match the target. Fail the build loudly
// instead of shipping a broken folder.
const staged = JSON.parse(
  readFileSync(new URL(`../${outDir}/manifest.json`, import.meta.url), "utf8"),
);
const scripts = [
  ...(Array.isArray(staged.background?.scripts) ? staged.background.scripts : []),
  ...(typeof staged.background?.service_worker === "string"
    ? [staged.background.service_worker]
    : []),
  ...staged.content_scripts.flatMap((cs) => cs.js),
];
for (const rel of scripts) {
  if (rel.startsWith("dist/")) {
    throw new Error(`[build:${target}] non-self-contained script path: ${rel}`);
  }
  const ref = new URL(`../${outDir}/${rel}`, import.meta.url);
  const stats = statSync(ref);
  if (!stats.size) throw new Error(`[build:${target}] empty output: ${ref.pathname}`);
}
if (isFirefox && typeof staged.background.service_worker === "string") {
  throw new Error(`[build:${target}] firefox manifest must use background.scripts`);
}
if (!isFirefox && typeof staged.background.service_worker !== "string") {
  throw new Error(`[build:${target}] chrome manifest must use background.service_worker`);
}
console.log(`[build:${target}] ${outDir}/ OK (${scripts.length} scripts verified)`);
