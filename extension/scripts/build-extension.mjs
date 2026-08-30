// Extension build: content scripts MUST be self-contained classic scripts —
// Chrome content_scripts don't support ES module imports (SyntaxError on
// injection). So each content entry gets its own single-input IIFE build
// (shared deps like kernel/backend-endpoint get inlined per file), while the
// service worker stays an ES module (manifest declares "type": "module").
//
// Targets (--target=chrome|firefox or TARGET env var, default chrome):
//   chrome  → dist/          unchanged: ES-module service worker + verbatim
//                            manifest copy (README/验收文档均指向该路径).
//   firefox → dist-firefox/  IIFE background (Firefox MV3 has no service
//                            worker; background.scripts loads a classic
//                            script) + derived Gecko manifest variant.
import { build } from "vite";
import { fileURLToPath } from "node:url";
import { copyFileSync, readFileSync, statSync, writeFileSync } from "node:fs";
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

// 3. Stage manifest into the loadable folder root ("Load unpacked" points at
// dist/, about:debugging points at dist-firefox/manifest.json). Chrome copies
// the source manifest verbatim; Firefox derives the Gecko variant (shared
// logic in src/shared/firefox.ts keeps this in sync with unit tests).
if (isFirefox) {
  const base = JSON.parse(
    readFileSync(new URL("../manifest.json", import.meta.url), "utf8"),
  );
  writeFileSync(
    new URL(`../${outDir}/manifest.json`, import.meta.url),
    `${JSON.stringify(buildFirefoxManifest(base), null, 2)}\n`,
  );
} else {
  copyFileSync(
    new URL("../manifest.json", import.meta.url),
    new URL(`../${outDir}/manifest.json`, import.meta.url),
  );
}

// 4. Smoke check the staged artifact: manifest must parse, every referenced
// script must exist and be non-empty, and the background shape must match the
// target. Fail the build loudly instead of shipping a broken folder.
// Resolution root per target = where the browser actually loads from: the
// repo root for chrome (paths keep their "dist/" prefix) and dist-firefox/
// for firefox (the variant strips the prefix).
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
  const ref = new URL(isFirefox ? `../${outDir}/${rel}` : `../${rel}`, import.meta.url);
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
